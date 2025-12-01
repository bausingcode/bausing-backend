from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    sku = db.Column(db.String(100))
    category_id = db.Column(UUID(as_uuid=True), db.ForeignKey('categories.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relaciones
    variants = db.relationship('ProductVariant', backref='product', lazy=True, cascade='all, delete-orphan')

    def get_min_price(self, locality_id=None):
        """Obtiene el precio mínimo del producto, opcionalmente filtrado por localidad"""
        from sqlalchemy import func
        query = db.session.query(func.min(ProductPrice.price)).join(
            ProductVariant, ProductPrice.product_variant_id == ProductVariant.id
        ).filter(ProductVariant.product_id == self.id)
        
        if locality_id:
            query = query.filter(ProductPrice.locality_id == locality_id)
        
        result = query.scalar()
        return float(result) if result else None
    
    def get_max_price(self, locality_id=None):
        """Obtiene el precio máximo del producto, opcionalmente filtrado por localidad"""
        from sqlalchemy import func
        query = db.session.query(func.max(ProductPrice.price)).join(
            ProductVariant, ProductPrice.product_variant_id == ProductVariant.id
        ).filter(ProductVariant.product_id == self.id)
        
        if locality_id:
            query = query.filter(ProductPrice.locality_id == locality_id)
        
        result = query.scalar()
        return float(result) if result else None
    
    def has_stock(self):
        """Verifica si el producto tiene stock disponible"""
        return any(variant.stock > 0 for variant in self.variants)
    
    def get_total_stock(self):
        """Obtiene el stock total del producto sumando todas las variantes"""
        return sum(variant.stock for variant in self.variants)
    
    def get_main_image(self):
        """Obtiene la imagen principal del producto (primera por posición)"""
        if self.images:
            sorted_images = sorted(self.images, key=lambda x: x.position)
            return sorted_images[0].image_url if sorted_images else None
        return None
    
    def to_dict(self, include_variants=False, include_images=False, locality_id=None, include_promos=False):
        data = {
            'id': str(self.id),
            'name': self.name,
            'description': self.description,
            'sku': self.sku,
            'category_id': str(self.category_id) if self.category_id else None,
            'category_name': self.category.name if self.category else None,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'has_stock': self.has_stock(),
            'total_stock': self.get_total_stock()
        }
        
        # Precios
        if locality_id:
            min_price = self.get_min_price(locality_id)
            max_price = self.get_max_price(locality_id)
        else:
            min_price = self.get_min_price()
            max_price = self.get_max_price()
        
        if min_price is not None:
            data['min_price'] = min_price
            data['max_price'] = max_price
            data['price_range'] = min_price if min_price == max_price else f"{min_price} - {max_price}"
        
        # Imagen principal (siempre incluir)
        main_image = self.get_main_image()
        if main_image:
            data['main_image'] = main_image
        
        # Todas las imágenes
        if include_images:
            sorted_images = sorted(self.images, key=lambda x: x.position)
            data['images'] = [img.to_dict() for img in sorted_images]
        
        # Variantes
        if include_variants:
            data['variants'] = [variant.to_dict(include_prices=True) for variant in self.variants]
        
        # Promociones aplicables
        if include_promos:
            from models.promo import Promo, PromoApplicability
            from datetime import datetime
            
            now = datetime.utcnow()
            applicable_promos = []
            
            # Buscar promociones que aplican a este producto
            promo_applicabilities = PromoApplicability.query.filter(
                db.or_(
                    PromoApplicability.applies_to == 'all',
                    db.and_(
                        PromoApplicability.applies_to == 'product',
                        PromoApplicability.product_id == self.id
                    ),
                    db.and_(
                        PromoApplicability.applies_to == 'category',
                        PromoApplicability.category_id == self.category_id
                    )
                )
            ).all()
            
            for app in promo_applicabilities:
                promo = Promo.query.get(app.promo_id)
                if promo and promo.is_valid():
                    applicable_promos.append(promo.to_dict())
            
            data['promos'] = applicable_promos
        
        return data


class ProductVariant(db.Model):
    __tablename__ = 'product_variants'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey('products.id'), nullable=False)
    variant_name = db.Column(db.String(255), nullable=False)
    stock = db.Column(db.Integer, default=0, nullable=False)
    # Atributos estructurados para variantes complejas (tamaño, combo, modelo, color, etc.)
    attributes = db.Column(db.JSON, nullable=True)

    # Relaciones
    prices = db.relationship('ProductPrice', backref='product_variant', lazy=True, cascade='all, delete-orphan')

    def to_dict(self, include_prices=False):
        data = {
            'id': str(self.id),
            'product_id': str(self.product_id),
            'variant_name': self.variant_name,
            'stock': self.stock,
            'attributes': self.attributes or {}
        }
        if include_prices:
            data['prices'] = [price.to_dict() for price in self.prices]
        return data
    
    def get_display_name(self):
        """Genera un nombre de visualización basado en los atributos"""
        if not self.attributes:
            return self.variant_name
        
        parts = []
        if self.attributes.get('size'):
            parts.append(self.attributes['size'])
        if self.attributes.get('combo'):
            parts.append(self.attributes['combo'])
        if self.attributes.get('model'):
            parts.append(self.attributes['model'])
        if self.attributes.get('color'):
            parts.append(self.attributes['color'])
        if self.attributes.get('dimensions'):
            parts.append(self.attributes['dimensions'])
        
        return ' - '.join(parts) if parts else self.variant_name


class ProductPrice(db.Model):
    __tablename__ = 'product_prices'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_variant_id = db.Column(UUID(as_uuid=True), db.ForeignKey('product_variants.id'), nullable=False)
    locality_id = db.Column(UUID(as_uuid=True), db.ForeignKey('localities.id'), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)

    def to_dict(self):
        return {
            'id': str(self.id),
            'product_variant_id': str(self.product_variant_id),
            'locality_id': str(self.locality_id),
            'locality_name': self.locality.name if self.locality else None,
            'price': float(self.price)
        }

