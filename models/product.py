from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    technical_description = db.Column(db.Text)
    warranty_months = db.Column(db.Integer)
    warranty_description = db.Column(db.Text)
    materials = db.Column(db.Text)
    filling_type = db.Column(db.String(255))
    max_supported_weight_kg = db.Column(db.Integer)
    has_pillow_top = db.Column(db.Boolean, default=False)
    is_bed_in_box = db.Column(db.Boolean, default=False)
    mattress_firmness = db.Column(db.String(255))
    size_label = db.Column(db.String(255))
    sku = db.Column(db.String(100))
    crm_product_id = db.Column(db.Integer, unique=True, nullable=True)
    category_id = db.Column(UUID(as_uuid=True), db.ForeignKey('categories.id'), nullable=True)
    category_option_id = db.Column(UUID(as_uuid=True), db.ForeignKey('category_options.id'), nullable=True)
    is_combo = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relaciones
    variants = db.relationship('ProductVariant', backref='product', lazy=True, cascade='all, delete-orphan')
    category_option = db.relationship('CategoryOption', backref='products', lazy=True)

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
        # El stock está en las options, no en las variants
        for variant in self.variants:
            if any(option.stock > 0 for option in variant.options):
                return True
        return False
    
    def get_total_stock(self):
        """Obtiene el stock total del producto sumando todas las opciones de variantes"""
        # El stock está en las options, no en las variants
        total = 0
        for variant in self.variants:
            total += sum(option.stock for option in variant.options)
        return total
    
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
            'technical_description': self.technical_description,
            'warranty_months': self.warranty_months,
            'warranty_description': self.warranty_description,
            'materials': self.materials,
            'filling_type': self.filling_type,
            'max_supported_weight_kg': self.max_supported_weight_kg,
            'has_pillow_top': self.has_pillow_top,
            'is_bed_in_box': self.is_bed_in_box,
            'mattress_firmness': self.mattress_firmness,
            'size_label': self.size_label,
            'sku': self.sku,
            'crm_product_id': self.crm_product_id,
            'category_id': str(self.category_id) if self.category_id else None,
            'category_name': self.category.name if self.category else None,
            'category_option_id': str(self.category_option_id) if self.category_option_id else None,
            'category_option_value': self.category_option.value if self.category_option else None,
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
            data['variants'] = [variant.to_dict(include_prices=True, include_options=True) for variant in self.variants]
        
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
    sku = db.Column(db.String(100), nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relaciones
    prices = db.relationship('ProductPrice', backref='product_variant', lazy=True, cascade='all, delete-orphan')
    options = db.relationship('ProductVariantOption', backref='product_variant', lazy=True, cascade='all, delete-orphan')

    def to_dict(self, include_prices=False, include_options=False):
        data = {
            'id': str(self.id),
            'product_id': str(self.product_id),
            'sku': self.sku,
            'price': float(self.price) if self.price else None
        }
        if include_prices:
            data['prices'] = [price.to_dict() for price in self.prices]
        if include_options:
            data['options'] = [option.to_dict() for option in self.options]
        return data
    
    def get_display_name(self):
        """Genera un nombre de visualización basado en el SKU o un valor por defecto"""
        return self.sku or 'Variante'


class ProductVariantOption(db.Model):
    __tablename__ = 'product_variant_options'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_variant_id = db.Column(UUID(as_uuid=True), db.ForeignKey('product_variants.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    stock = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self, include_prices=False):
        data = {
            'id': str(self.id),
            'product_variant_id': str(self.product_variant_id),
            'name': self.name,
            'stock': self.stock,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if include_prices:
            data['prices'] = [price.to_dict() for price in self.prices]
        return data


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

