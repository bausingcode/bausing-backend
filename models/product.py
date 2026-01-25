from database import db
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid

# Cache para el catálogo "Cordoba capital" (se actualiza en cada request si es necesario)
_cordoba_capital_catalog_id = None

def get_cordoba_capital_catalog_id():
    """Obtiene el ID del catálogo 'Cordoba capital' con cache"""
    global _cordoba_capital_catalog_id
    if _cordoba_capital_catalog_id is None:
        from models.catalog import Catalog
        catalog = Catalog.query.filter_by(name='Cordoba capital').first()
        if catalog:
            _cordoba_capital_catalog_id = catalog.id
    return _cordoba_capital_catalog_id

def clear_catalog_cache():
    """Limpia el cache del catálogo (útil para testing o cuando se actualiza)"""
    global _cordoba_capital_catalog_id
    _cordoba_capital_catalog_id = None

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
    # Relación con subcategorías a través de la tabla de relación
    subcategory_associations = db.relationship('ProductSubcategory', backref='product', lazy=True, cascade='all, delete-orphan')
    
    def get_subcategories(self):
        """Obtiene las subcategorías asociadas al producto"""
        return [assoc.subcategory for assoc in self.subcategory_associations if assoc.subcategory]

    def get_min_price(self, locality_id=None):
        """Obtiene el precio mínimo del producto, opcionalmente filtrado por localidad (busca por catálogo).
        Si no hay locality_id, usa el catálogo 'Cordoba capital' por defecto."""
        from sqlalchemy import func
        import uuid as uuid_lib
        from models.catalog import LocalityCatalog, Catalog
        
        query = db.session.query(func.min(ProductPrice.price)).join(
            ProductVariantOption, ProductPrice.product_variant_id == ProductVariantOption.id
        ).join(
            ProductVariant, ProductVariantOption.product_variant_id == ProductVariant.id
        ).filter(ProductVariant.product_id == self.id)
        
        if locality_id:
            # Convertir locality_id a UUID si es string
            try:
                locality_uuid = uuid_lib.UUID(locality_id) if isinstance(locality_id, str) else locality_id
                # Buscar el catálogo de esta localidad
                locality_catalog = LocalityCatalog.query.filter_by(locality_id=locality_uuid).first()
                if locality_catalog:
                    # Filtrar por catalog_id (nuevo sistema)
                    query = query.filter(ProductPrice.catalog_id == locality_catalog.catalog_id)
                else:
                    # Compatibilidad hacia atrás: filtrar por locality_id
                    query = query.filter(ProductPrice.locality_id == locality_uuid)
            except (ValueError, TypeError) as e:
                print(f"[ERROR] Invalid locality_id format in get_min_price: {locality_id}, error: {e}")
                return 0.0
        else:
            # Si no hay localidad, usar el catálogo "Cordoba capital" por defecto
            cordoba_capital_catalog_id = get_cordoba_capital_catalog_id()
            if cordoba_capital_catalog_id:
                query = query.filter(ProductPrice.catalog_id == cordoba_capital_catalog_id)
        
        result = query.scalar()
        return float(result) if result else 0.0
    
    def get_max_price(self, locality_id=None):
        """Obtiene el precio máximo del producto, opcionalmente filtrado por localidad (busca por catálogo).
        Si no hay locality_id, usa el catálogo 'Cordoba capital' por defecto."""
        from sqlalchemy import func
        import uuid as uuid_lib
        from models.catalog import LocalityCatalog, Catalog
        
        query = db.session.query(func.max(ProductPrice.price)).join(
            ProductVariantOption, ProductPrice.product_variant_id == ProductVariantOption.id
        ).join(
            ProductVariant, ProductVariantOption.product_variant_id == ProductVariant.id
        ).filter(ProductVariant.product_id == self.id)
        
        if locality_id:
            # Convertir locality_id a UUID si es string
            try:
                locality_uuid = uuid_lib.UUID(locality_id) if isinstance(locality_id, str) else locality_id
                # Buscar el catálogo de esta localidad
                locality_catalog = LocalityCatalog.query.filter_by(locality_id=locality_uuid).first()
                if locality_catalog:
                    # Filtrar por catalog_id (nuevo sistema)
                    query = query.filter(ProductPrice.catalog_id == locality_catalog.catalog_id)
                else:
                    # Compatibilidad hacia atrás: filtrar por locality_id
                    query = query.filter(ProductPrice.locality_id == locality_uuid)
            except (ValueError, TypeError) as e:
                print(f"[ERROR] Invalid locality_id format in get_max_price: {locality_id}, error: {e}")
                return 0.0
        else:
            # Si no hay localidad, usar el catálogo "Cordoba capital" por defecto
            cordoba_capital_catalog_id = get_cordoba_capital_catalog_id()
            if cordoba_capital_catalog_id:
                query = query.filter(ProductPrice.catalog_id == cordoba_capital_catalog_id)
        
        result = query.scalar()
        return float(result) if result else 0.0
    
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
        """Obtiene la imagen principal del producto (primera por posición, luego por fecha de creación)"""
        if self.images:
            # Ordenar por posición (menor primero), y si hay empate, por created_at (más antigua primero)
            # Manejar None en position como si fuera 999999 para que vayan al final
            from datetime import datetime as dt
            sorted_images = sorted(
                self.images, 
                key=lambda x: (
                    x.position if x.position is not None else 999999,
                    x.created_at if x.created_at else dt.min.replace(tzinfo=timezone.utc)
                )
            )
            # Buscar la primera imagen con URL válida (debe ser la de menor posición)
            for img in sorted_images:
                if img and img.image_url and img.image_url.strip():
                    return img.image_url
        return None
    
    def to_dict(self, include_variants=False, include_images=False, locality_id=None, include_promos=False, locality_to_catalog_map=None):
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
            'subcategories': [assoc.to_dict() for assoc in self.subcategory_associations] if hasattr(self, 'subcategory_associations') else [],
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
        
        # Si no hay precio para la localidad, usar 0
        if min_price is None:
            min_price = 0.0
        if max_price is None:
            max_price = 0.0
        
        # Siempre incluir precios (incluso si son 0)
        data['min_price'] = float(min_price) if min_price is not None else 0.0
        data['max_price'] = float(max_price) if max_price is not None else 0.0
        
        if min_price > 0 or max_price > 0:
            data['price_range'] = min_price if min_price == max_price else f"{min_price} - {max_price}"
        else:
            data['price_range'] = "0"
        
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
            data['variants'] = [variant.to_dict(include_prices=True, include_options=True, locality_id=locality_id, locality_to_catalog_map=locality_to_catalog_map) for variant in self.variants]
        
        # Promociones aplicables
        if include_promos:
            from models.promo import Promo, PromoApplicability
            from datetime import datetime
            
            now = datetime.utcnow()
            applicable_promos = []
            
            # Buscar promociones que aplican a este producto
            # Construir la consulta de promociones con agrupación correcta
            # Limpiar transacción abortada antes de consultar
            try:
                from database import db
                db.session.rollback()
            except:
                pass
            
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
    # Nota: Los precios ahora están asociados a las opciones, no directamente a las variantes
    # Se mantiene esta relación por compatibilidad, pero debería deprecarse
    options = db.relationship('ProductVariantOption', backref='product_variant', lazy=True, cascade='all, delete-orphan')

    def to_dict(self, include_prices=False, include_options=False, locality_id=None, locality_to_catalog_map=None):
        data = {
            'id': str(self.id),
            'product_id': str(self.product_id),
            'sku': self.sku,
            'price': float(self.price) if self.price else None
        }
        if include_prices:
            # Los precios ahora están en las opciones, no en la variante directamente
            # Recopilar todos los precios de todas las opciones (por catálogo)
            all_prices = []
            for option in self.options:
                # Mostrar precios por catálogo (preferir catalog_id sobre locality_id)
                option_prices = []
                for price in option.prices:
                    # Priorizar precios con catalog_id, pero mantener compatibilidad con locality_id
                    if price.catalog_id:
                        option_prices.append(price.to_dict())
                    elif price.locality_id and not any(p.get('catalog_id') for p in option_prices):
                        # Solo agregar precios por localidad si no hay precios por catálogo
                        option_prices.append(price.to_dict())
                
                # Si se especifica locality_id, intentar encontrar el catálogo correspondiente
                if locality_id:
                    import uuid as uuid_lib
                    try:
                        locality_uuid = uuid_lib.UUID(locality_id) if isinstance(locality_id, str) else locality_id
                        # Buscar el catálogo de esta localidad (usar mapa si está disponible para optimizar)
                        catalog_id = None
                        if locality_to_catalog_map:
                            catalog_id = locality_to_catalog_map.get(str(locality_uuid))
                        
                        if catalog_id:
                            locality_catalog = type('obj', (object,), {'catalog_id': catalog_id})()
                        else:
                            from models.catalog import LocalityCatalog
                            locality_catalog = LocalityCatalog.query.filter_by(locality_id=locality_uuid).first()
                        if locality_catalog:
                            # Filtrar precios por el catálogo de esta localidad
                            catalog_prices = [p for p in option_prices if p.get('catalog_id') == str(locality_catalog.catalog_id)]
                            if catalog_prices:
                                all_prices.extend(catalog_prices)
                            else:
                                # Si no hay precio para este catálogo, buscar por localidad (compatibilidad)
                                locality_prices = [price.to_dict() for price in option.prices if price.locality_id == locality_uuid]
                                all_prices.extend(locality_prices if locality_prices else [{
                                    'id': None,
                                    'product_variant_id': str(option.id),
                                    'product_variant_option_id': str(option.id),
                                    'catalog_id': str(locality_catalog.catalog_id),
                                    'catalog_name': None,
                                    'price': 0.0
                                }])
                        else:
                            # Si no hay catálogo para esta localidad, usar precios por localidad (compatibilidad)
                            locality_prices = [price.to_dict() for price in option.prices if price.locality_id == locality_uuid]
                            all_prices.extend(locality_prices if locality_prices else [{
                                'id': None,
                                'product_variant_id': str(option.id),
                                'product_variant_option_id': str(option.id),
                                'locality_id': str(locality_uuid),
                                'locality_name': None,
                                'price': 0.0
                            }])
                    except (ValueError, TypeError) as e:
                        print(f"[ERROR] Invalid locality_id format in ProductVariant.to_dict: {locality_id}, error: {e}")
                        all_prices.extend(option_prices)
                else:
                    # Sin filtro de localidad, mostrar todos los precios por catálogo
                    all_prices.extend(option_prices)
            data['prices'] = all_prices
        if include_options:
            data['options'] = [option.to_dict(include_prices=include_prices, locality_id=locality_id, locality_to_catalog_map=locality_to_catalog_map) for option in self.options]
        return data
    
    def get_display_name(self):
        """Genera un nombre de visualización basado en el SKU o un valor por defecto"""
        return self.sku or 'Variante'


class ProductSubcategory(db.Model):
    """Tabla de relación muchos-a-muchos entre productos y subcategorías"""
    __tablename__ = 'product_subcategories'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    subcategory_id = db.Column(UUID(as_uuid=True), db.ForeignKey('categories.id', ondelete='CASCADE'), nullable=False)
    category_option_id = db.Column(UUID(as_uuid=True), db.ForeignKey('category_options.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relaciones
    subcategory = db.relationship('Category', backref='product_subcategories', lazy=True)
    category_option = db.relationship('CategoryOption', backref='product_subcategories', lazy=True)

    # Constraint único para evitar duplicados
    # Permite múltiples opciones para la misma subcategoría: (product_id, subcategory_id, category_option_id)
    __table_args__ = (db.UniqueConstraint('product_id', 'subcategory_id', 'category_option_id', name='unique_product_subcategory_option'),)

    def to_dict(self):
        return {
            'id': str(self.id),
            'product_id': str(self.product_id),
            'subcategory_id': str(self.subcategory_id),
            'subcategory_name': self.subcategory.name if self.subcategory else None,
            'category_option_id': str(self.category_option_id) if self.category_option_id else None,
            'category_option_value': self.category_option.value if self.category_option else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ProductVariantOption(db.Model):
    __tablename__ = 'product_variant_options'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_variant_id = db.Column(UUID(as_uuid=True), db.ForeignKey('product_variants.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    stock = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relación con precios
    prices = db.relationship('ProductPrice', backref='product_variant_option', lazy=True, cascade='all, delete-orphan')

    def to_dict(self, include_prices=False, locality_id=None, locality_to_catalog_map=None):
        data = {
            'id': str(self.id),
            'product_variant_id': str(self.product_variant_id),
            'name': self.name,
            'stock': self.stock,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if include_prices:
            import uuid as uuid_lib
            # Priorizar precios por catálogo sobre precios por localidad
            catalog_prices = [price.to_dict() for price in self.prices if price.catalog_id]
            locality_prices = [price.to_dict() for price in self.prices if price.locality_id and not price.catalog_id]
            
            if locality_id:
                # Filtrar precios por localidad (buscar su catálogo)
                try:
                    locality_uuid = uuid_lib.UUID(locality_id) if isinstance(locality_id, str) else locality_id
                    # Buscar el catálogo de esta localidad (usar mapa si está disponible para optimizar)
                    catalog_id = None
                    if locality_to_catalog_map:
                        catalog_id = locality_to_catalog_map.get(str(locality_uuid))
                    
                    if catalog_id:
                        # Usar el catalog_id del mapa
                        filtered_prices = [p for p in catalog_prices if p.get('catalog_id') == catalog_id]
                        if not filtered_prices:
                            # Si no hay precio para este catálogo, buscar por localidad (compatibilidad)
                            filtered_prices = [p for p in locality_prices if p.get('locality_id') == str(locality_uuid)]
                            if not filtered_prices:
                                filtered_prices = [{
                                    'id': None,
                                    'product_variant_id': str(self.id),
                                    'product_variant_option_id': str(self.id),
                                    'catalog_id': catalog_id,
                                    'catalog_name': None,
                                    'price': 0.0
                                }]
                        data['prices'] = filtered_prices
                        # Agregar precio específico del catálogo (para fácil acceso)
                        import uuid as uuid_lib
                        catalog_uuid = uuid_lib.UUID(catalog_id) if isinstance(catalog_id, str) else catalog_id
                        price_for_catalog = next((p for p in self.prices if p.catalog_id == catalog_uuid), None)
                        data['price'] = float(price_for_catalog.price) if price_for_catalog else 0.0
                    else:
                        from models.catalog import LocalityCatalog
                        locality_catalog = LocalityCatalog.query.filter_by(locality_id=locality_uuid).first()
                        if locality_catalog:
                            # Filtrar precios por el catálogo de esta localidad
                            filtered_prices = [p for p in catalog_prices if p.get('catalog_id') == str(locality_catalog.catalog_id)]
                            if not filtered_prices:
                                # Si no hay precio para este catálogo, buscar por localidad (compatibilidad)
                                filtered_prices = [p for p in locality_prices if p.get('locality_id') == str(locality_uuid)]
                                if not filtered_prices:
                                    filtered_prices = [{
                                        'id': None,
                                        'product_variant_id': str(self.id),
                                        'product_variant_option_id': str(self.id),
                                        'catalog_id': str(locality_catalog.catalog_id),
                                        'catalog_name': None,
                                        'price': 0.0
                                    }]
                            data['prices'] = filtered_prices
                            # Agregar precio específico del catálogo (para fácil acceso)
                            price_for_catalog = next((p for p in self.prices if p.catalog_id == locality_catalog.catalog_id), None)
                            data['price'] = float(price_for_catalog.price) if price_for_catalog else 0.0
                        else:
                            # Si no hay catálogo para esta localidad, usar precios por localidad (compatibilidad)
                            filtered_prices = [p for p in locality_prices if p.get('locality_id') == str(locality_uuid)]
                        if not filtered_prices:
                            filtered_prices = [{
                                'id': None,
                                'product_variant_id': str(self.id),
                                'product_variant_option_id': str(self.id),
                                'locality_id': str(locality_uuid),
                                'locality_name': None,
                                'price': 0.0
                            }]
                        data['prices'] = filtered_prices
                        # Agregar precio específico de la localidad (para fácil acceso)
                        price_for_locality = next((p for p in self.prices if p.locality_id == locality_uuid), None)
                        data['price'] = float(price_for_locality.price) if price_for_locality else 0.0
                except (ValueError, TypeError) as e:
                    print(f"[ERROR] Invalid locality_id format in ProductVariantOption.to_dict: {locality_id}, error: {e}")
                    # Mostrar todos los precios por catálogo, o por localidad si no hay catálogos
                    data['prices'] = catalog_prices if catalog_prices else locality_prices
                    data['price'] = 0.0
            else:
                # Sin filtro de localidad, usar el catálogo "Cordoba capital" por defecto
                cordoba_capital_catalog_id = get_cordoba_capital_catalog_id()
                if cordoba_capital_catalog_id:
                    # Filtrar precios por el catálogo "Cordoba capital"
                    filtered_prices = [p for p in catalog_prices if p.get('catalog_id') == str(cordoba_capital_catalog_id)]
                    if filtered_prices:
                        data['prices'] = filtered_prices
                        data['price'] = min(float(p.get('price', 0)) for p in filtered_prices if p.get('price'))
                    else:
                        # Si no hay precios para "Cordoba capital", mostrar todos los precios por catálogo
                        data['prices'] = catalog_prices + locality_prices
                        if catalog_prices:
                            data['price'] = min(float(p.get('price', 0)) for p in catalog_prices if p.get('price'))
                        elif locality_prices:
                            data['price'] = min(float(p.get('price', 0)) for p in locality_prices if p.get('price'))
                        else:
                            data['price'] = 0.0
                else:
                    # Si no existe el catálogo "Cordoba capital", mostrar todos los precios
                    data['prices'] = catalog_prices + locality_prices
                    if catalog_prices:
                        data['price'] = min(float(p.get('price', 0)) for p in catalog_prices if p.get('price'))
                    elif locality_prices:
                        data['price'] = min(float(p.get('price', 0)) for p in locality_prices if p.get('price'))
                    else:
                        data['price'] = 0.0
        return data


class ProductPrice(db.Model):
    __tablename__ = 'product_prices'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # product_variant_id ahora apunta a product_variant_options.id (no a product_variants.id)
    product_variant_id = db.Column(UUID(as_uuid=True), db.ForeignKey('product_variant_options.id', ondelete='CASCADE'), nullable=False)
    locality_id = db.Column(UUID(as_uuid=True), db.ForeignKey('localities.id'), nullable=True)  # Mantener por compatibilidad temporal
    catalog_id = db.Column(UUID(as_uuid=True), db.ForeignKey('catalogs.id', ondelete='CASCADE'), nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)

    def to_dict(self):
        data = {
            'id': str(self.id),
            'product_variant_id': str(self.product_variant_id),  # Este ID ahora es de product_variant_options
            'product_variant_option_id': str(self.product_variant_id),  # Alias para compatibilidad
            'price': float(self.price)
        }
        
        # Incluir información de localidad si existe (compatibilidad hacia atrás)
        if self.locality_id:
            data['locality_id'] = str(self.locality_id)
            try:
                data['locality_name'] = self.locality.name if self.locality else None
            except Exception:
                # Si hay un error al cargar la localidad (ej: transacción abortada), usar None
                data['locality_name'] = None
        
        # Incluir información de catálogo
        if self.catalog_id:
            data['catalog_id'] = str(self.catalog_id)
            try:
                data['catalog_name'] = self.catalog.name if self.catalog else None
            except Exception:
                # Si hay un error al cargar el catálogo (ej: columna faltante, transacción abortada), usar None
                data['catalog_name'] = None
        
        return data

