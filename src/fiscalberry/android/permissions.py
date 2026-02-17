#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Helper para gestionar permisos de Android en runtime
Sistema mejorado con callbacks para manejar respuestas del usuario
"""

from fiscalberry.common.fiscalberry_logger import getLogger
import time
from typing import Callable, Optional, List, Dict

logger = getLogger("AndroidPermissions")

# Callbacks globales para notificar cambios en permisos
_permission_granted_callbacks = []
_permission_denied_callbacks = []

# Detectar si estamos en Android y obtener información de la versión
ANDROID = False
ANDROID_API_LEVEL = 0
try:
    from android.permissions import request_permissions, check_permission, Permission
    from jnius import autoclass
    ANDROID = True
    
    # Obtener el nivel de API actual
    try:
        BuildVersion = autoclass('android.os.Build$VERSION')
        ANDROID_API_LEVEL = BuildVersion.SDK_INT
        logger.debug(f"Módulo de permisos Android disponible - API Level: {ANDROID_API_LEVEL}")
    except Exception as e:
        logger.warning(f"No se pudo obtener API Level: {e}")
        ANDROID_API_LEVEL = 23  # Asumir API 23 (Android 6.0) como mínimo
        logger.debug(f"Usando API Level por defecto: {ANDROID_API_LEVEL}")
except ImportError:
    logger.debug("android.permissions no disponible - no es Android")


# Mapeo de permisos necesarios para Fiscalberry por versión de API
FISCALBERRY_PERMISSIONS_BASE = [
    'android.permission.INTERNET',
    'android.permission.ACCESS_NETWORK_STATE',
    'android.permission.ACCESS_WIFI_STATE',
    'android.permission.WAKE_LOCK',
    'android.permission.BLUETOOTH',
    'android.permission.BLUETOOTH_ADMIN',
]

# Permisos adicionales según versión de API
FISCALBERRY_PERMISSIONS_API_23_PLUS = [
    'android.permission.ACCESS_COARSE_LOCATION',  # Requerido para Bluetooth desde API 23
]

FISCALBERRY_PERMISSIONS_API_28_PLUS = [
    'android.permission.FOREGROUND_SERVICE',  # Requerido desde API 28
]

# API 29+: Ubicación en background requerida para BT scan en segundo plano
FISCALBERRY_PERMISSIONS_API_29_PLUS = [
    'android.permission.ACCESS_BACKGROUND_LOCATION',
]

FISCALBERRY_PERMISSIONS_API_31_PLUS = [
    'android.permission.ACCESS_FINE_LOCATION',  # Requerido para BLUETOOTH_SCAN
    'android.permission.BLUETOOTH_CONNECT',  # Nuevos permisos de Bluetooth desde API 31
    'android.permission.BLUETOOTH_SCAN',
]

# API 33+: Permiso explícito para notificaciones (incluyendo foreground service)
FISCALBERRY_PERMISSIONS_API_33_PLUS = [
    'android.permission.POST_NOTIFICATIONS',
]

# Permisos de almacenamiento (deprecados en Android 13+)
# Solo necesarios en Android 12 y anteriores para guardar config.ini y logs
FISCALBERRY_PERMISSIONS_STORAGE_LEGACY = [
    'android.permission.READ_EXTERNAL_STORAGE',
    'android.permission.WRITE_EXTERNAL_STORAGE',
]


def get_required_permissions():
    """
    Obtiene la lista de permisos requeridos según la versión de Android.
    
    NOTA: Esta función devuelve TODOS los permisos juntos (legacy).
    Para solicitud por etapas, usar get_core_permissions() y get_background_permissions().
    
    Returns:
        list: Lista de permisos requeridos para la versión actual
    """
    if not ANDROID:
        return []
    
    permissions = FISCALBERRY_PERMISSIONS_BASE.copy()
    
    # Permisos de almacenamiento solo para Android 12 y anteriores
    # En Android 13+ (API 33+) estos permisos están deprecados
    if ANDROID_API_LEVEL < 33:  # Solo Android 12 y anteriores
        permissions.extend(FISCALBERRY_PERMISSIONS_STORAGE_LEGACY)
        logger.debug(f"Android {ANDROID_API_LEVEL} < 33: agregando permisos de almacenamiento legacy")
    else:
        logger.debug(f"Android {ANDROID_API_LEVEL} >= 33: permisos de almacenamiento no necesarios")
    
    # Agregar permisos según nivel de API
    if ANDROID_API_LEVEL >= 23:  # Android 6.0+
        permissions.extend(FISCALBERRY_PERMISSIONS_API_23_PLUS)
        
    if ANDROID_API_LEVEL >= 28:  # Android 9.0+
        permissions.extend(FISCALBERRY_PERMISSIONS_API_28_PLUS)
    
    if ANDROID_API_LEVEL >= 29:  # Android 10.0+
        permissions.extend(FISCALBERRY_PERMISSIONS_API_29_PLUS)
        logger.debug(f"Android {ANDROID_API_LEVEL} >= 29: agregando ACCESS_BACKGROUND_LOCATION")
        
    if ANDROID_API_LEVEL >= 31:  # Android 12.0+
        permissions.extend(FISCALBERRY_PERMISSIONS_API_31_PLUS)
    
    if ANDROID_API_LEVEL >= 33:  # Android 13.0+
        permissions.extend(FISCALBERRY_PERMISSIONS_API_33_PLUS)
        logger.debug(f"Android {ANDROID_API_LEVEL} >= 33: agregando POST_NOTIFICATIONS")
    
    logger.debug(f"Permisos requeridos para API {ANDROID_API_LEVEL}: {permissions}")
    return permissions


# Mantener compatibilidad con código existente
FISCALBERRY_PERMISSIONS = get_required_permissions()


def get_core_permissions():
    """
    Permisos críticos que se solicitan primero (Etapa 1).
    NO incluye ACCESS_BACKGROUND_LOCATION ni POST_NOTIFICATIONS.
    
    Incluye:
    - Internet y red
    - Bluetooth básico
    - Ubicación FOREGROUND (COARSE/FINE)
    - Bluetooth moderno (CONNECT/SCAN)
    - Foreground Service
    - Almacenamiento (solo Android 12-)
    
    Returns:
        list: Permisos core para la versión actual
    """
    if not ANDROID:
        return []
    
    permissions = [
        'android.permission.INTERNET',
        'android.permission.ACCESS_NETWORK_STATE',
        'android.permission.ACCESS_WIFI_STATE',
        'android.permission.WAKE_LOCK',
        'android.permission.BLUETOOTH',
        'android.permission.BLUETOOTH_ADMIN',
    ]
    
    # Almacenamiento solo en Android 12 y anteriores
    if ANDROID_API_LEVEL < 33:
        permissions.extend([
            'android.permission.READ_EXTERNAL_STORAGE',
            'android.permission.WRITE_EXTERNAL_STORAGE',
        ])
        logger.debug(f"Core: agregando permisos de almacenamiento (API {ANDROID_API_LEVEL})")
    
    # Ubicación FOREGROUND (requerida para Bluetooth en API 23+)
    if ANDROID_API_LEVEL >= 23:
        permissions.append('android.permission.ACCESS_COARSE_LOCATION')
        logger.debug("Core: agregando ACCESS_COARSE_LOCATION")
    
    if ANDROID_API_LEVEL >= 28:
        permissions.append('android.permission.FOREGROUND_SERVICE')
        logger.debug("Core: agregando FOREGROUND_SERVICE")
    
    # Bluetooth moderno + Ubicación FINE (API 31+)
    if ANDROID_API_LEVEL >= 31:
        permissions.extend([
            'android.permission.ACCESS_FINE_LOCATION',  # Requerido para BLUETOOTH_SCAN
            'android.permission.BLUETOOTH_CONNECT',
            'android.permission.BLUETOOTH_SCAN',
        ])
        logger.debug("Core: agregando Bluetooth moderno + ACCESS_FINE_LOCATION")
    
    logger.debug(f"Permisos core para API {ANDROID_API_LEVEL}: {len(permissions)} permisos")
    return permissions


def get_background_permissions():
    """
    Permisos sensibles que se solicitan DESPUÉS de los core (Etapa 2).
    
    CRÍTICO: Solo incluye ACCESS_BACKGROUND_LOCATION si los permisos
    foreground (FINE o COARSE) ya están otorgados.
    
    Incluye:
    - Ubicación BACKGROUND (solo si foreground otorgado)
    - SCHEDULE_EXACT_ALARM  (por ahora fue retirado por no ser necesario y tirar errores)
    
    Returns:
        list: Permisos background para la versión actual
    """
    if not ANDROID:
        return []
    
    permissions = []
    
    # Ubicación BACKGROUND (API 29+)
    # CRÍTICO: Solo solicitar si ACCESS_FINE_LOCATION o ACCESS_COARSE_LOCATION ya están otorgados
    if ANDROID_API_LEVEL >= 29:
        # Verificar que al menos uno de los permisos foreground esté otorgado
        has_foreground = (
            check_permission('android.permission.ACCESS_FINE_LOCATION') or
            check_permission('android.permission.ACCESS_COARSE_LOCATION')
        )
        if has_foreground:
            permissions.append('android.permission.ACCESS_BACKGROUND_LOCATION')
            logger.debug("Background: agregando ACCESS_BACKGROUND_LOCATION (foreground otorgado)")
        else:
            logger.warning("Background: ACCESS_BACKGROUND_LOCATION omitido (foreground no otorgado)")
    
    logger.debug(f"Permisos background para API {ANDROID_API_LEVEL}: {len(permissions)} permisos")
    return permissions


def get_notification_permissions():
    """
    Permisos de notificaciones (Etapa 3).
    
    NOTA: Ya se maneja en fiscalberry_app.py con _request_notification_permission(),
    pero incluido aquí para completitud.
    
    Returns:
        list: Permisos de notificaciones para la versión actual
    """
    if not ANDROID:
        return []
    
    if ANDROID_API_LEVEL >= 33:
        logger.debug("Notification: agregando POST_NOTIFICATIONS")
        return ['android.permission.POST_NOTIFICATIONS']
    
    return []



def is_permission_supported(permission):
    """
    Verifica si un permiso es soportado en la versión actual de Android.
    
    Args:
        permission (str): Nombre del permiso
        
    Returns:
        bool: True si el permiso es soportado
    """
    if not ANDROID:
        return True  # En desarrollo, asumimos que sí
    
    # Permisos que requieren API específica
    api_requirements = {
        'android.permission.FOREGROUND_SERVICE': 28,
        'android.permission.BLUETOOTH_CONNECT': 31,
        'android.permission.BLUETOOTH_SCAN': 31,
        'android.permission.ACCESS_COARSE_LOCATION': 23,
    }
    
    required_api = api_requirements.get(permission, 1)  # API 1 por defecto
    supported = ANDROID_API_LEVEL >= required_api
    
    if not supported:
        logger.debug(f"Permiso {permission} requiere API {required_api}, actual: {ANDROID_API_LEVEL}")
    
    return supported


def add_permission_granted_callback(callback: Callable):
    """Registra callback para cuando se otorga un permiso"""
    if callback not in _permission_granted_callbacks:
        _permission_granted_callbacks.append(callback)
        logger.debug(f"Callback registrado: {callback.__name__}")


def add_permission_denied_callback(callback: Callable):
    """Registra callback para cuando se deniega un permiso"""
    if callback not in _permission_denied_callbacks:
        _permission_denied_callbacks.append(callback)
        logger.debug(f"Callback registrado: {callback.__name__}")


def remove_permission_callback(callback: Callable):
    """Elimina un callback registrado"""
    if callback in _permission_granted_callbacks:
        _permission_granted_callbacks.remove(callback)
    if callback in _permission_denied_callbacks:
        _permission_denied_callbacks.remove(callback)


def check_all_permissions():
    """
    Verifica si todos los permisos necesarios están otorgados.
    
    Returns:
        dict: Diccionario con el estado de cada permiso
    """
    if not ANDROID:
        return {'all_granted': True, 'details': {}, 'missing': []}
    
    try:
        required_permissions = get_required_permissions()
        results = {}
        missing = []
        all_granted = True
        
        for permission in required_permissions:
            try:
                # Convertir string de permiso a objeto Permission si es posible
                granted = check_permission(permission)
                results[permission] = granted
                
                if not granted:
                    all_granted = False
                    missing.append(permission)
                    logger.warning(f"Permiso no otorgado: {permission}")
                else:
                    logger.debug(f"Permiso otorgado: {permission}")
                    
            except Exception as e:
                logger.error(f"Error verificando permiso {permission}: {e}")
                results[permission] = False
                missing.append(permission)
                all_granted = False
        
        return {
            'all_granted': all_granted,
            'details': results,
            'missing': missing,
            'missing_count': len(missing),
            'api_level': ANDROID_API_LEVEL,
            'total_permissions': len(required_permissions)
        }
        
    except Exception as e:
        logger.error(f"Error verificando permisos: {e}", exc_info=True)
        return {'all_granted': False, 'details': {}, 'missing': []}



def request_all_permissions(callback_on_complete: Optional[Callable] = None):
    """
    Solicita permisos en etapas para cumplir con restricciones de Android 11+.
    
    Etapa 1: Core permissions (Bluetooth, Internet, Ubicación Foreground)
    Etapa 2: Background permissions (solo si Foreground fue otorgado)
    Etapa 3: Notifications (manejado en fiscalberry_app.py)
    
    Args:
        callback_on_complete: Función a llamar cuando se complete la solicitud
    
    Returns:
        bool: True si se solicitaron los permisos correctamente
    """
    if not ANDROID:
        logger.debug("No es Android - permisos no necesarios")
        if callback_on_complete:
            callback_on_complete(True)
        return True
    
    try:
        logger.info("🔐 Iniciando solicitud de permisos por etapas...")
        
        # ETAPA 1: Permisos Core
        core_permissions = get_core_permissions()
        missing_core = [p for p in core_permissions if not check_permission(p)]
        
        if missing_core:
            logger.info(f"📱 Etapa 1: Solicitando {len(missing_core)} permisos core...")
            logger.debug(f"Permisos core faltantes: {missing_core}")
            _request_permissions_stage(
                missing_core,
                lambda success: _on_core_permissions_granted(success, callback_on_complete)
            )
        else:
            logger.debug("✅ Permisos core ya otorgados")
            # Pasar directamente a etapa 2
            _request_background_permissions(callback_on_complete)
        
        return True
        
    except Exception as e:
        logger.error(f"Error en solicitud de permisos: {e}", exc_info=True)
        if callback_on_complete:
            callback_on_complete(False)
        return False


def _on_core_permissions_granted(success, final_callback):
    """Callback después de solicitar permisos core."""
    if success:
        logger.info("✅ Permisos core otorgados")
    else:
        logger.warning("⚠️ Algunos permisos core fueron denegados")
    
    # Continuar con permisos background de todas formas
    # (puede que algunos core se hayan otorgado)
    _request_background_permissions(final_callback)


def _request_background_permissions(final_callback):
    """Solicita permisos background (Etapa 2)."""
    try:
        background_permissions = get_background_permissions()
        
        if not background_permissions:
            logger.debug("No hay permisos background para solicitar")
            if final_callback:
                final_callback(True)
            return
        
        missing_background = [p for p in background_permissions if not check_permission(p)]
        
        if missing_background:
            logger.info(f"📱 Etapa 2: Solicitando {len(missing_background)} permisos background...")
            logger.debug(f"Permisos background faltantes: {missing_background}")
            
            # IMPORTANTE: Delay de 1 segundo antes de solicitar background
            # Esto da tiempo al usuario a procesar los diálogos anteriores
            from kivy.clock import Clock
            Clock.schedule_once(
                lambda dt: _request_permissions_stage(missing_background, final_callback),
                1.0
            )
        else:
            logger.debug("✅ Permisos background ya otorgados")
            if final_callback:
                final_callback(True)
                
    except Exception as e:
        logger.error(f"Error solicitando permisos background: {e}")
        if final_callback:
            final_callback(False)


def _request_permissions_stage(permissions, callback):
    """
    Solicita un conjunto de permisos y ejecuta callback al completar.
    
    Args:
        permissions: Lista de permisos a solicitar
        callback: Función a llamar después de solicitar (recibe bool success)
    """
    try:
        logger.debug(f"Solicitando {len(permissions)} permisos...")
        
        # Método 1: request_permissions de python-for-android
        try:
            logger.debug("Intentando con request_permissions()...")
            request_permissions(permissions)
            logger.debug("✓ request_permissions() ejecutado")
        except Exception as e1:
            logger.warning(f"request_permissions() falló: {e1}")
            
            # Método 2: ActivityCompat
            try:
                logger.debug("Intentando con ActivityCompat...")
                _request_permissions_via_activity_compat(permissions)
            except Exception as e2:
                logger.error(f"ActivityCompat también falló: {e2}")
        
        # Programar verificación después de 2 segundos
        if callback:
            from kivy.clock import Clock
            Clock.schedule_once(lambda dt: _verify_and_callback(callback), 2)
        
    except Exception as e:
        logger.error(f"Error en _request_permissions_stage: {e}")
        if callback:
            callback(False)



def _verify_and_callback(callback: Callable):
    """Verifica permisos y ejecuta callback"""
    try:
        status = check_all_permissions()
        success = status['all_granted']
        
        if success:
            logger.info("✅ Todos los permisos otorgados")
            for cb in _permission_granted_callbacks:
                try:
                    cb()
                except Exception as e:
                    logger.error(f"Error en callback granted: {e}")
        else:
            logger.warning(f"⚠️ {status['missing_count']} permisos faltantes")
            for cb in _permission_denied_callbacks:
                try:
                    cb(status['missing'])
                except Exception as e:
                    logger.error(f"Error en callback denied: {e}")
        
        callback(success)
    except Exception as e:
        logger.error(f"Error en verificación: {e}")
        callback(False)


def _request_permissions_via_activity_compat(permissions):
    """
    Solicita permisos usando ActivityCompat directamente (método alternativo).
    Esto es necesario en Android 12+ para Bluetooth.
    """
    try:
        from jnius import autoclass
        
        # Obtener la actividad actual
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        activity = PythonActivity.mActivity
        
        if not activity:
            logger.error("No se pudo obtener PythonActivity")
            return
        
        logger.debug(f"Activity obtenida: {activity}")
        
        # Usar ActivityCompat para solicitar permisos
        ActivityCompat = autoclass('androidx.core.app.ActivityCompat')
        
        # Convertir lista Python a array Java
        String = autoclass('java.lang.String')
        permissions_array = [String(p) for p in permissions]
        
        logger.debug(f"Solicitando {len(permissions_array)} permisos vía ActivityCompat...")
        
        # Request code arbitrario
        REQUEST_CODE = 1001
        
        # Solicitar permisos
        ActivityCompat.requestPermissions(
            activity,
            permissions_array,
            REQUEST_CODE
        )
        
        logger.debug("✓ ActivityCompat.requestPermissions() ejecutado")
        logger.info("⚠️ El usuario debe aprobar los permisos en el diálogo que apareció")
        
    except Exception as e:
        logger.error(f"Error en _request_permissions_via_activity_compat: {e}", exc_info=True)


def request_storage_permissions():
    """Solicita permisos de almacenamiento (para guardar config.ini y logs)"""
    if not ANDROID:
        return True
    
    try:
        permissions = [
            'android.permission.READ_EXTERNAL_STORAGE',
            'android.permission.WRITE_EXTERNAL_STORAGE',
        ]
        
        missing = [p for p in permissions if not check_permission(p)]
        if missing:
            logger.debug("Solicitando permisos de almacenamiento...")
            request_permissions(missing)
        return True
    except Exception as e:
        logger.error(f"Error solicitando permisos de almacenamiento: {e}")
        return False


def request_network_permissions():
    """Solicita permisos de red (para RabbitMQ y SocketIO)"""
    if not ANDROID:
        return True
    
    try:
        permissions = [
            'android.permission.INTERNET',
            'android.permission.ACCESS_NETWORK_STATE',
            'android.permission.ACCESS_WIFI_STATE',
        ]
        
        missing = [p for p in permissions if not check_permission(p)]
        if missing:
            logger.debug("Solicitando permisos de red...")
            request_permissions(missing)
        return True
    except Exception as e:
        logger.error(f"Error solicitando permisos de red: {e}")
        return False


def request_bluetooth_permissions():
    """
    Solicita permisos de Bluetooth (para impresoras BT).
    CRÍTICO: Android 12+ requiere BLUETOOTH_CONNECT y BLUETOOTH_SCAN.
    """
    if not ANDROID:
        return True
    
    try:
        permissions = [
            'android.permission.BLUETOOTH',
            'android.permission.BLUETOOTH_ADMIN',
            'android.permission.BLUETOOTH_CONNECT',
            'android.permission.BLUETOOTH_SCAN',
            'android.permission.ACCESS_COARSE_LOCATION',
            'android.permission.ACCESS_FINE_LOCATION',
        ]
        
        missing = [p for p in permissions if not check_permission(p)]
        if missing:
            logger.debug(f"⚠️ Solicitando {len(missing)} permisos de Bluetooth...")
            logger.debug("Lista de permisos faltantes:")
            for p in missing:
                logger.debug(f"  - {p}")
            
            # Intentar ambos métodos
            try:
                request_permissions(missing)
                logger.debug("✓ request_permissions() ejecutado para Bluetooth")
            except Exception as e:
                logger.warning(f"request_permissions() falló: {e}")
                try:
                    _request_permissions_via_activity_compat(missing)
                except Exception as e2:
                    logger.error(f"ActivityCompat también falló: {e2}")
        else:
            logger.debug("✓ Todos los permisos de Bluetooth ya otorgados")
            
        return True
    except Exception as e:
        logger.error(f"Error solicitando permisos de Bluetooth: {e}", exc_info=True)
        return False

def request_notification_permission_native():
    """
    Solicita permiso POST_NOTIFICATIONS usando el diálogo nativo de Android.
    Solo para Android 13+ (API 33+).
    
    Returns:
        bool: True si el permiso ya está otorgado o se solicitó correctamente
    """
    if not ANDROID:
        return True
    
    if ANDROID_API_LEVEL < 33:
        logger.debug("Android < 13: POST_NOTIFICATIONS no requerido")
        return True
    
    try:
        # Verificar si ya está otorgado
        if check_permission('android.permission.POST_NOTIFICATIONS'):
            logger.debug("POST_NOTIFICATIONS ya otorgado")
            return True
        
        from jnius import autoclass
        
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        Settings = autoclass('android.provider.Settings')
        Intent = autoclass('android.content.Intent')
        
        activity = PythonActivity.mActivity
        if not activity:
            logger.warning("Activity no disponible")
            return False
        
        logger.info("⚠️ Solicitando permiso POST_NOTIFICATIONS...")
        
        # Abrir configuración de notificaciones de la app
        intent = Intent()
        intent.setAction(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
        intent.putExtra(Settings.EXTRA_APP_PACKAGE, activity.getPackageName())
        
        activity.startActivity(intent)
        logger.debug("Configuración de notificaciones abierta")
        return True
        
    except Exception as e:
        logger.error(f"Error solicitando POST_NOTIFICATIONS: {e}", exc_info=True)
        return False

def get_permissions_status_summary():
    """
    Obtiene un resumen legible del estado de los permisos.
    
    Returns:
        str: Resumen en texto del estado de permisos
    """
    if not ANDROID:
        return "Plataforma: No Android\nPermisos: No requeridos"
    
    status = check_all_permissions()
    
    summary = "Estado de Permisos Android:\n"
    summary += "="*50 + "\n"
    
    if status['all_granted']:
        summary += "✅ Todos los permisos otorgados\n"
    else:
        summary += "⚠️ Algunos permisos faltantes\n\n"
        
        for permission, granted in status['details'].items():
            status_icon = "✅" if granted else "❌"
            perm_name = permission.split('.')[-1]
            summary += f"  {status_icon} {perm_name}\n"
    
    return summary


if __name__ == "__main__":
    # Test del módulo
    print(get_permissions_status_summary())
    
    if ANDROID:
        print("\nSolicitando permisos faltantes...")
        request_all_permissions()
