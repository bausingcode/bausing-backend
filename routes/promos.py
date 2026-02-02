from flask import Blueprint, request, jsonify
from database import db
from models.promo import Promo, PromoApplicability
from sqlalchemy.exc import IntegrityError
from datetime import datetime
import uuid
from routes.admin import admin_required

promos_bp = Blueprint('promos', __name__)

@promos_bp.route('', methods=['GET'])
def get_promos():
    """Obtener todas las promociones"""
    try:
        is_active = request.args.get('is_active')
        include_applicability = request.args.get('include_applicability', 'false').lower() == 'true'
        valid_only = request.args.get('valid_only', 'false').lower() == 'true'
        
        query = Promo.query
        
        if is_active is not None:
            query = query.filter_by(is_active=is_active.lower() == 'true')
        
        if valid_only:
            now = datetime.utcnow()
            query = query.filter(
                Promo.is_active == True,
                Promo.start_at <= now,
                Promo.end_at >= now
            )
        
        # Ordenar por id (created_at puede no existir en la tabla)
        promos = query.order_by(Promo.id.desc()).all()
        
        return jsonify({
            'success': True,
            'data': [promo.to_dict(include_applicability=include_applicability) for promo in promos]
        }), 200
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print("=" * 50)
        print("ERROR in get_promos:")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        print("Traceback:")
        print(error_trace)
        print("=" * 50)
        return jsonify({
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__,
            'traceback': error_trace if request.args.get('debug') == 'true' else None
        }), 500

@promos_bp.route('/<uuid:promo_id>', methods=['GET'])
def get_promo(promo_id):
    """Obtener una promoción por ID"""
    try:
        include_applicability = request.args.get('include_applicability', 'true').lower() == 'true'
        promo = Promo.query.get_or_404(promo_id)
        
        return jsonify({
            'success': True,
            'data': promo.to_dict(include_applicability=include_applicability)
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404

@promos_bp.route('', methods=['POST'])
@admin_required
def create_promo():
    """Crear una nueva promoción"""
    try:
        data = request.get_json()
        
        if not data or not data.get('title'):
            return jsonify({
                'success': False,
                'error': 'El título es requerido'
            }), 400
        
        if not data.get('type'):
            return jsonify({
                'success': False,
                'error': 'El tipo de promoción es requerido'
            }), 400
        
        # El valor solo es requerido si no es promotional_message
        if data.get('type') != 'promotional_message' and data.get('value') is None:
            return jsonify({
                'success': False,
                'error': 'El valor es requerido para este tipo de promoción'
            }), 400
        
        # Validar fechas
        start_at = datetime.fromisoformat(data['start_at'].replace('Z', '+00:00')) if data.get('start_at') else None
        end_at = datetime.fromisoformat(data['end_at'].replace('Z', '+00:00')) if data.get('end_at') else None
        
        if not start_at or not end_at:
            return jsonify({
                'success': False,
                'error': 'Las fechas de inicio y fin son requeridas'
            }), 400
        
        if start_at >= end_at:
            return jsonify({
                'success': False,
                'error': 'La fecha de inicio debe ser anterior a la fecha de fin'
            }), 400
        
        promo = Promo(
            title=data['title'],
            description=data.get('description'),
            type=data['type'],
            value=data.get('value') if data.get('type') != 'promotional_message' else None,
            extra_config=data.get('extra_config'),
            start_at=start_at,
            end_at=end_at,
            is_active=data.get('is_active', True),
            allows_wallet=data.get('allows_wallet', True)
        )
        
        db.session.add(promo)
        db.session.flush()  # Para obtener el ID antes del commit
        
        # Crear reglas de aplicabilidad si se proporcionan
        applicability_list = data.get('applicability', [])
        for app_data in applicability_list:
            applies_to = app_data.get('applies_to', 'all')
            
            if applies_to == 'all':
                applicability = PromoApplicability(
                    promo_id=promo.id,
                    applies_to='all'
                )
            elif applies_to == 'product':
                if not app_data.get('product_id'):
                    return jsonify({
                        'success': False,
                        'error': 'product_id es requerido cuando applies_to es "product"'
                    }), 400
                applicability = PromoApplicability(
                    promo_id=promo.id,
                    product_id=app_data['product_id'],
                    applies_to='product'
                )
            elif applies_to == 'category':
                if not app_data.get('category_id'):
                    return jsonify({
                        'success': False,
                        'error': 'category_id es requerido cuando applies_to es "category"'
                    }), 400
                applicability = PromoApplicability(
                    promo_id=promo.id,
                    category_id=app_data['category_id'],
                    applies_to='category'
                )
            # elif applies_to == 'variant':
            #     # Variant support disabled - column doesn't exist in DB
            #     if not app_data.get('product_variant_id'):
            #         return jsonify({
            #             'success': False,
            #             'error': 'product_variant_id es requerido cuando applies_to es "variant"'
            #         }), 400
            #     applicability = PromoApplicability(
            #         promo_id=promo.id,
            #         product_variant_id=app_data['product_variant_id'],
            #         applies_to='variant'
            #     )
            else:
                return jsonify({
                    'success': False,
                    'error': f'applies_to inválido: {applies_to}'
                }), 400
            
            db.session.add(applicability)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': promo.to_dict(include_applicability=True)
        }), 201
    except ValueError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Error en formato de fecha: {str(e)}'
        }), 400
    except IntegrityError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Error de integridad: ' + str(e)
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@promos_bp.route('/<uuid:promo_id>', methods=['PUT'])
@admin_required
def update_promo(promo_id):
    """Actualizar una promoción"""
    try:
        promo = Promo.query.get_or_404(promo_id)
        data = request.get_json()
        
        if 'title' in data:
            promo.title = data['title']
        if 'description' in data:
            promo.description = data.get('description')
        if 'type' in data:
            promo.type = data['type']
        if 'value' in data:
            # Si el tipo es promotional_message, el valor debe ser None
            if data.get('type') == 'promotional_message':
                promo.value = None
            else:
                promo.value = data['value']
        elif 'type' in data and data['type'] == 'promotional_message':
            # Si solo se cambia el tipo a promotional_message, establecer value a None
            promo.value = None
        
        # Manejar extra_config: limpiar custom_message si no se proporciona o si el tipo cambia
        if 'extra_config' in data:
            new_extra_config = data.get('extra_config') or {}
            # Si el tipo no es promotional_message, percentage o fixed, eliminar custom_message
            promo_type = data.get('type', promo.type)
            if promo_type not in ['promotional_message', 'percentage', 'fixed']:
                if isinstance(new_extra_config, dict):
                    new_extra_config.pop('custom_message', None)
            # Si extra_config está vacío, establecer como None para limpiar
            if not new_extra_config or (isinstance(new_extra_config, dict) and len(new_extra_config) == 0):
                promo.extra_config = None
            else:
                promo.extra_config = new_extra_config
        if 'start_at' in data:
            promo.start_at = datetime.fromisoformat(data['start_at'].replace('Z', '+00:00'))
        if 'end_at' in data:
            promo.end_at = datetime.fromisoformat(data['end_at'].replace('Z', '+00:00'))
        if 'is_active' in data:
            promo.is_active = data.get('is_active')
        if 'allows_wallet' in data:
            promo.allows_wallet = data.get('allows_wallet', True)
        
        # Validar fechas si ambas están presentes
        if promo.start_at and promo.end_at and promo.start_at >= promo.end_at:
            return jsonify({
                'success': False,
                'error': 'La fecha de inicio debe ser anterior a la fecha de fin'
            }), 400
        
        # Actualizar aplicabilidad si se proporciona
        if 'applicability' in data:
            # Eliminar aplicabilidades existentes
            PromoApplicability.query.filter_by(promo_id=promo.id).delete()
            
            # Crear nuevas aplicabilidades
            for app_data in data['applicability']:
                applies_to = app_data.get('applies_to', 'all')
                
                if applies_to == 'all':
                    applicability = PromoApplicability(
                        promo_id=promo.id,
                        applies_to='all'
                    )
                elif applies_to == 'product':
                    applicability = PromoApplicability(
                        promo_id=promo.id,
                        product_id=app_data.get('product_id'),
                        applies_to='product'
                    )
                elif applies_to == 'category':
                    applicability = PromoApplicability(
                        promo_id=promo.id,
                        category_id=app_data.get('category_id'),
                        applies_to='category'
                    )
                # elif applies_to == 'variant':
                #     # Variant support disabled - column doesn't exist in DB
                #     applicability = PromoApplicability(
                #         promo_id=promo.id,
                #         product_variant_id=app_data.get('product_variant_id'),
                #         applies_to='variant'
                #     )
                else:
                    continue
                
                db.session.add(applicability)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': promo.to_dict(include_applicability=True)
        }), 200
    except ValueError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Error en formato de fecha: {str(e)}'
        }), 400
    except IntegrityError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Error de integridad: ' + str(e)
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@promos_bp.route('/<uuid:promo_id>', methods=['DELETE'])
@admin_required
def delete_promo(promo_id):
    """Eliminar una promoción"""
    try:
        promo = Promo.query.get_or_404(promo_id)
        
        db.session.delete(promo)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Promoción eliminada correctamente'
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@promos_bp.route('/<uuid:promo_id>/toggle-active', methods=['PATCH'])
@admin_required
def toggle_promo_active(promo_id):
    """Activar/desactivar una promoción"""
    try:
        promo = Promo.query.get_or_404(promo_id)
        promo.is_active = not promo.is_active
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': promo.to_dict(include_applicability=True)
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@promos_bp.route('/applicable', methods=['GET'])
def get_applicable_promos():
    """Obtener promociones aplicables a un producto, categoría o variante"""
    try:
        product_id = request.args.get('product_id')
        category_id = request.args.get('category_id')
        product_variant_id = request.args.get('product_variant_id')
        
        if not any([product_id, category_id, product_variant_id]):
            return jsonify({
                'success': False,
                'error': 'Se requiere al menos uno de: product_id, category_id, product_variant_id'
            }), 400
        
        now = datetime.utcnow()
        
        # Buscar promociones activas y vigentes
        promos_query = Promo.query.filter(
            Promo.is_active == True,
            Promo.start_at <= now,
            Promo.end_at >= now
        )
        
        applicable_promos = []
        
        for promo in promos_query.all():
            is_applicable = False
            
            for app in promo.applicability:
                if app.applies_to == 'all':
                    is_applicable = True
                    break
                elif app.applies_to == 'product' and product_id and str(app.product_id) == product_id:
                    is_applicable = True
                    break
                elif app.applies_to == 'category' and category_id and str(app.category_id) == category_id:
                    is_applicable = True
                    break
                # elif app.applies_to == 'variant' and product_variant_id and str(app.product_variant_id) == product_variant_id:
                #     is_applicable = True
                #     break
            
            if is_applicable:
                applicable_promos.append(promo)
        
        return jsonify({
            'success': True,
            'data': [promo.to_dict(include_applicability=True) for promo in applicable_promos]
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

