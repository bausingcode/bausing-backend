from database import db
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid

class SaleRetryQueue(db.Model):
    """Modelo para la tabla de reintentos de ventas al CRM"""
    __tablename__ = 'sale_retry_queue'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Referencia a la orden original (opcional, puede ser NULL si falla antes de crear la orden)
    order_id = db.Column(UUID(as_uuid=True), db.ForeignKey('orders.id'), nullable=True)
    
    # Estado del reintento
    status = db.Column(db.String(50), nullable=False, default='pending')  # 'pending', 'processing', 'completed', 'failed', 'cancelled'
    
    # Contador de reintentos
    retry_count = db.Column(db.Integer, nullable=False, default=0)
    max_retries = db.Column(db.Integer, nullable=False, default=5)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_retry_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Mensaje de error (si falla)
    error_message = db.Column(db.Text, nullable=True)
    error_details = db.Column(JSONB, nullable=True)
    
    # Payload completo que se envía al CRM (JSONB para flexibilidad)
    crm_payload = db.Column(JSONB, nullable=False)
    
    # Campos específicos del payload para facilitar consultas (extraídos del JSONB)
    fecha_detalle = db.Column(db.Date, nullable=True)
    tipo_venta = db.Column(db.Integer, nullable=True)
    cliente_nombre = db.Column(db.String(255), nullable=True)
    cliente_email = db.Column(db.String(255), nullable=True)
    provincia_id = db.Column(db.Integer, nullable=True)
    zona_id = db.Column(db.Integer, nullable=True)
    monto_total = db.Column(db.Numeric(10, 2), nullable=True)
    payment_method = db.Column(db.String(50), nullable=True)
    payment_processed = db.Column(db.Boolean, nullable=True)
    
    # Metadata adicional
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=True)
    priority = db.Column(db.Integer, default=0, nullable=False)  # Para priorizar ciertos reintentos
    
    # Relaciones
    order = db.relationship('Order', backref='sale_retries', lazy=True)
    user = db.relationship('User', backref='sale_retries', lazy=True)

    def to_dict(self):
        """Convierte el registro a diccionario"""
        return {
            'id': str(self.id),
            'order_id': str(self.order_id) if self.order_id else None,
            'status': self.status,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_retry_at': self.last_retry_at.isoformat() if self.last_retry_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error_message': self.error_message,
            'error_details': self.error_details,
            'crm_payload': self.crm_payload,
            'fecha_detalle': self.fecha_detalle.isoformat() if self.fecha_detalle else None,
            'tipo_venta': self.tipo_venta,
            'cliente_nombre': self.cliente_nombre,
            'cliente_email': self.cliente_email,
            'provincia_id': self.provincia_id,
            'zona_id': self.zona_id,
            'monto_total': float(self.monto_total) if self.monto_total else None,
            'payment_method': self.payment_method,
            'payment_processed': self.payment_processed,
            'user_id': str(self.user_id) if self.user_id else None,
            'priority': self.priority
        }
