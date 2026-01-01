from database import db
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid

# Importar Order para que SQLAlchemy pueda resolver la foreign key
# Se importa aquí para evitar importación circular, pero Order debe estar
# importado en algún lugar (app.py) antes de que SQLAlchemy procese las foreign keys
try:
    from .order import Order  # noqa: F401
except ImportError:
    pass  # Order será importado en app.py a través de models.__init__

class Wallet(db.Model):
    __tablename__ = 'wallets'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False, unique=True)
    balance = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    is_blocked = db.Column(db.Boolean, default=False, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relaciones
    user = db.relationship('User', backref='wallet', uselist=False)
    movements = db.relationship('WalletMovement', backref='wallet', lazy=True, order_by='WalletMovement.created_at')

    def to_dict(self):
        """Convierte la billetera a diccionario"""
        return {
            'id': str(self.id),
            'user_id': str(self.user_id),
            'balance': float(self.balance) if self.balance else 0.0,
            'is_blocked': self.is_blocked,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class WalletMovement(db.Model):
    __tablename__ = 'wallet_movements'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wallet_id = db.Column(UUID(as_uuid=True), db.ForeignKey('wallets.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # 'credit', 'debit', 'payment', 'cashback', 'refund', 'manual_credit', 'manual_debit'
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    description = db.Column(db.Text)
    order_id = db.Column(UUID(as_uuid=True), db.ForeignKey('orders.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)  # Fecha de vencimiento del movimiento
    
    # Nota: Los campos admin_user_id, reason, internal_comment no existen en la BD
    # La información del admin se guarda en audit_logs en su lugar

    def to_dict(self, include_admin=False):
        """Convierte el movimiento a diccionario"""
        data = {
            'id': str(self.id),
            'wallet_id': str(self.wallet_id),
            'type': self.type,
            'amount': float(self.amount) if self.amount else 0.0,
            'description': self.description,
            'order_id': str(self.order_id) if self.order_id else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None
        }
        
        # Intentar obtener información del admin desde audit_logs si se requiere
        if include_admin:
            try:
                # Buscar el log de auditoría más reciente para este movimiento
                # Buscamos por wallet_id, amount y tipo de acción que coincida con el tipo de movimiento
                action_map = {
                    'manual_credit': 'wallet_manual_credit',
                    'manual_debit': 'wallet_manual_debit'
                }
                action_type = action_map.get(self.type, None)
                
                query = AuditLog.query.filter_by(
                    entity='wallet',
                    entity_id=self.wallet_id
                ).filter(
                    AuditLog.details['amount'].astext == str(self.amount)
                )
                
                if action_type:
                    query = query.filter(AuditLog.action == action_type)
                
                audit_log = query.filter(
                    AuditLog.created_at <= self.created_at
                ).order_by(AuditLog.created_at.desc()).first()
                
                if audit_log and audit_log.admin_user:
                    data['admin_user'] = {
                        'id': str(audit_log.admin_user.id),
                        'email': audit_log.admin_user.email
                    }
                    # Si hay detalles en el audit log, incluir reason y internal_comment
                    if audit_log.details:
                        if 'reason' in audit_log.details:
                            data['reason'] = audit_log.details.get('reason')
                        if 'internal_comment' in audit_log.details:
                            data['internal_comment'] = audit_log.details.get('internal_comment')
            except Exception as e:
                # Si hay error obteniendo el admin, simplemente no incluirlo
                print(f"DEBUG: Error obteniendo admin para movimiento {self.id}: {str(e)}")
                import traceback
                print(f"DEBUG TRACEBACK: {traceback.format_exc()}")
                pass
        
        return data


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('admin_users.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)  # 'wallet_credit', 'wallet_debit', 'wallet_block', etc.
    entity = db.Column(db.String(50), nullable=False)  # 'wallet', 'order', etc.
    entity_id = db.Column(UUID(as_uuid=True), nullable=True)
    details = db.Column(JSONB, nullable=True)  # Información adicional en formato JSON
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relaciones
    admin_user = db.relationship('AdminUser', backref='audit_logs', lazy=True)

    def to_dict(self):
        """Convierte el log de auditoría a diccionario"""
        return {
            'id': str(self.id),
            'user_id': str(self.user_id),
            'action': self.action,
            'entity': self.entity,
            'entity_id': str(self.entity_id) if self.entity_id else None,
            'details': self.details,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'admin_user': {
                'id': str(self.admin_user.id),
                'email': self.admin_user.email
            } if self.admin_user else None
        }

