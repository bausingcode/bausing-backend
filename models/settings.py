from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

class SystemSettings(db.Model):
    __tablename__ = 'system_settings'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = db.Column(db.String(255), nullable=False, unique=True)
    value = db.Column(db.Text, nullable=False)
    value_type = db.Column(db.String(50), nullable=False)  # 'number', 'boolean', 'string', 'json'
    category = db.Column(db.String(100), nullable=False)  # 'wallet', 'security', 'general'
    description = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(UUID(as_uuid=True), db.ForeignKey('admin_users.id'), nullable=True)

    def to_dict(self):
        return {
            'id': str(self.id),
            'key': self.key,
            'value': self.value,
            'value_type': self.value_type,
            'category': self.category,
            'description': self.description,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'updated_by': str(self.updated_by) if self.updated_by else None
        }

    @staticmethod
    def get_value(key, default=None):
        """Obtiene el valor de una configuración"""
        setting = SystemSettings.query.filter_by(key=key).first()
        if not setting:
            return default
        
        if setting.value_type == 'number':
            try:
                return float(setting.value)
            except ValueError:
                return default
        elif setting.value_type == 'boolean':
            return setting.value.lower() in ('true', '1', 'yes', 'on')
        elif setting.value_type == 'json':
            import json
            try:
                return json.loads(setting.value)
            except:
                return default
        else:
            return setting.value

    @staticmethod
    def set_value(key, value, value_type, category, description=None, updated_by=None):
        """Establece o actualiza el valor de una configuración"""
        setting = SystemSettings.query.filter_by(key=key).first()
        
        if setting:
            setting.value = str(value)
            setting.value_type = value_type
            setting.category = category
            if description:
                setting.description = description
            if updated_by:
                setting.updated_by = updated_by
            setting.updated_at = datetime.utcnow()
        else:
            setting = SystemSettings(
                key=key,
                value=str(value),
                value_type=value_type,
                category=category,
                description=description,
                updated_by=updated_by
            )
            db.session.add(setting)
        
        return setting


class MessageTemplate(db.Model):
    __tablename__ = 'message_templates'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = db.Column(db.String(100), nullable=False, unique=True)
    subject = db.Column(db.String(255))
    body = db.Column(db.Text, nullable=False)
    variables = db.Column(db.JSON)  # Variables disponibles
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(UUID(as_uuid=True), db.ForeignKey('admin_users.id'), nullable=True)

    def to_dict(self):
        return {
            'id': str(self.id),
            'type': self.type,
            'subject': self.subject,
            'body': self.body,
            'variables': self.variables,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'updated_by': str(self.updated_by) if self.updated_by else None
        }


class NotificationSetting(db.Model):
    __tablename__ = 'notification_settings'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('admin_users.id'), nullable=False)
    notification_type = db.Column(db.String(100), nullable=False)
    enabled = db.Column(db.Boolean, default=True)
    channel = db.Column(db.String(50), default='email')  # 'email', 'sms', 'push', 'in_app'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('admin_user_id', 'notification_type', 'channel', name='unique_notification_setting'),
    )

    def to_dict(self):
        return {
            'id': str(self.id),
            'admin_user_id': str(self.admin_user_id),
            'notification_type': self.notification_type,
            'enabled': self.enabled,
            'channel': self.channel,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class SecuritySetting(db.Model):
    __tablename__ = 'security_settings'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = db.Column(db.String(255), nullable=False, unique=True)
    value = db.Column(db.Text, nullable=False)
    value_type = db.Column(db.String(50), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(UUID(as_uuid=True), db.ForeignKey('admin_users.id'), nullable=True)

    def to_dict(self):
        return {
            'id': str(self.id),
            'key': self.key,
            'value': self.value,
            'value_type': self.value_type,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'updated_by': str(self.updated_by) if self.updated_by else None
        }

    @staticmethod
    def get_value(key, default=None):
        """Obtiene el valor de una configuración de seguridad"""
        setting = SecuritySetting.query.filter_by(key=key).first()
        if not setting:
            return default
        
        if setting.value_type == 'number':
            try:
                return float(setting.value)
            except ValueError:
                return default
        elif setting.value_type == 'boolean':
            return setting.value.lower() in ('true', '1', 'yes', 'on')
        else:
            return setting.value

    @staticmethod
    def set_value(key, value, value_type, updated_by=None):
        """Establece o actualiza el valor de una configuración de seguridad"""
        setting = SecuritySetting.query.filter_by(key=key).first()
        
        if setting:
            setting.value = str(value)
            setting.value_type = value_type
            if updated_by:
                setting.updated_by = updated_by
            setting.updated_at = datetime.utcnow()
        else:
            setting = SecuritySetting(
                key=key,
                value=str(value),
                value_type=value_type,
                updated_by=updated_by
            )
            db.session.add(setting)
        
        return setting

