from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

class Referral(db.Model):
    __tablename__ = 'referrals'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    referrer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    referred_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    order_id = db.Column(UUID(as_uuid=True), db.ForeignKey('orders.id'), nullable=False, unique=True)
    credit_amount = db.Column(db.Numeric(10, 2), nullable=False)
    credited = db.Column(db.Boolean, default=False, nullable=False)
    credited_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relaciones
    referrer = db.relationship('User', foreign_keys=[referrer_id], backref='referrals_made', lazy=True)
    referred = db.relationship('User', foreign_keys=[referred_id], backref='referrals_received', lazy=True)
    order = db.relationship('Order', backref='referral', uselist=False, lazy=True)

    def to_dict(self, include_users=False):
        """Convierte el referido a diccionario"""
        data = {
            'id': str(self.id),
            'referrer_id': str(self.referrer_id),
            'referred_id': str(self.referred_id),
            'order_id': str(self.order_id),
            'credit_amount': float(self.credit_amount) if self.credit_amount else 0.0,
            'credited': self.credited,
            'credited_at': self.credited_at.isoformat() if self.credited_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        
        if include_users:
            if self.referrer:
                data['referrer'] = {
                    'id': str(self.referrer.id),
                    'first_name': self.referrer.first_name,
                    'last_name': self.referrer.last_name,
                    'email': self.referrer.email
                }
            if self.referred:
                data['referred'] = {
                    'id': str(self.referred.id),
                    'first_name': self.referred.first_name,
                    'last_name': self.referred.last_name,
                    'email': self.referred.email
                }
            if self.order:
                data['order'] = {
                    'id': str(self.order.id),
                    'total': float(self.order.total) if self.order.total else 0.0,
                    'created_at': self.order.created_at.isoformat() if self.order.created_at else None
                }
        
        return data
