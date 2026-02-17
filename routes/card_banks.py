from flask import Blueprint, request, jsonify
from database import db
from models.card_type import CardType
from models.bank import Bank
from models.card_bank_installment import CardBankInstallment
from sqlalchemy.exc import IntegrityError
from routes.admin import admin_required
import uuid

card_banks_bp = Blueprint('card_banks', __name__)

# ==================== CARD TYPES ====================

@card_banks_bp.route('/card-types', methods=['GET'])
def get_card_types():
    """Obtener todos los tipos de tarjeta (público)"""
    try:
        db.session.rollback()
        
        only_active = request.args.get('only_active', 'true').lower() == 'true'
        query = CardType.query
        
        if only_active:
            query = query.filter_by(is_active=True)
        
        card_types = query.order_by(CardType.display_order, CardType.name).all()
        
        return jsonify({
            'success': True,
            'data': [ct.to_dict() for ct in card_types]
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@card_banks_bp.route('/card-types/<uuid:card_type_id>', methods=['GET'])
def get_card_type(card_type_id):
    """Obtener un tipo de tarjeta por ID"""
    try:
        card_type = CardType.query.get_or_404(card_type_id)
        return jsonify({
            'success': True,
            'data': card_type.to_dict(include_installments=True)
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404

@card_banks_bp.route('/admin/card-types', methods=['POST'])
@admin_required
def create_card_type():
    """Crear un nuevo tipo de tarjeta (admin)"""
    try:
        data = request.get_json()
        
        if not data or not data.get('code') or not data.get('name'):
            return jsonify({
                'success': False,
                'error': 'El código y nombre son requeridos'
            }), 400
        
        card_type = CardType(
            code=data['code'],
            name=data['name'],
            is_active=data.get('is_active', True),
            display_order=data.get('display_order', 0)
        )
        
        db.session.add(card_type)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': card_type.to_dict()
        }), 201
    except IntegrityError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Ya existe un tipo de tarjeta con ese código'
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@card_banks_bp.route('/admin/card-types/<uuid:card_type_id>', methods=['PUT'])
@admin_required
def update_card_type(card_type_id):
    """Actualizar un tipo de tarjeta (admin)"""
    try:
        card_type = CardType.query.get_or_404(card_type_id)
        data = request.get_json()
        
        if 'code' in data:
            card_type.code = data['code']
        if 'name' in data:
            card_type.name = data['name']
        if 'is_active' in data:
            card_type.is_active = data['is_active']
        if 'display_order' in data:
            card_type.display_order = data['display_order']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': card_type.to_dict()
        }), 200
    except IntegrityError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Ya existe un tipo de tarjeta con ese código'
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@card_banks_bp.route('/admin/card-types/<uuid:card_type_id>', methods=['DELETE'])
@admin_required
def delete_card_type(card_type_id):
    """Eliminar un tipo de tarjeta (admin)"""
    try:
        card_type = CardType.query.get_or_404(card_type_id)
        db.session.delete(card_type)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Tipo de tarjeta eliminado correctamente'
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ==================== BANKS ====================

@card_banks_bp.route('/banks', methods=['GET'])
def get_banks():
    """Obtener todos los bancos (público)"""
    try:
        db.session.rollback()
        
        only_active = request.args.get('only_active', 'true').lower() == 'true'
        query = Bank.query
        
        if only_active:
            query = query.filter_by(is_active=True)
        
        banks = query.order_by(Bank.display_order, Bank.name).all()
        
        return jsonify({
            'success': True,
            'data': [b.to_dict() for b in banks]
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@card_banks_bp.route('/banks/<uuid:bank_id>', methods=['GET'])
def get_bank(bank_id):
    """Obtener un banco por ID"""
    try:
        bank = Bank.query.get_or_404(bank_id)
        return jsonify({
            'success': True,
            'data': bank.to_dict(include_installments=True)
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404

@card_banks_bp.route('/admin/banks', methods=['POST'])
@admin_required
def create_bank():
    """Crear un nuevo banco (admin)"""
    try:
        data = request.get_json()
        
        if not data or not data.get('name'):
            return jsonify({
                'success': False,
                'error': 'El nombre es requerido'
            }), 400
        
        bank = Bank(
            name=data['name'],
            is_active=data.get('is_active', True),
            display_order=data.get('display_order', 0)
        )
        
        db.session.add(bank)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': bank.to_dict()
        }), 201
    except IntegrityError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Ya existe un banco con ese nombre'
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@card_banks_bp.route('/admin/banks/<uuid:bank_id>', methods=['PUT'])
@admin_required
def update_bank(bank_id):
    """Actualizar un banco (admin)"""
    try:
        bank = Bank.query.get_or_404(bank_id)
        data = request.get_json()
        
        if 'name' in data:
            bank.name = data['name']
        if 'is_active' in data:
            bank.is_active = data['is_active']
        if 'display_order' in data:
            bank.display_order = data['display_order']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': bank.to_dict()
        }), 200
    except IntegrityError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Ya existe un banco con ese nombre'
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@card_banks_bp.route('/admin/banks/<uuid:bank_id>', methods=['DELETE'])
@admin_required
def delete_bank(bank_id):
    """Eliminar un banco (admin)"""
    try:
        bank = Bank.query.get_or_404(bank_id)
        db.session.delete(bank)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Banco eliminado correctamente'
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ==================== INSTALLMENTS ====================

@card_banks_bp.route('/card-bank-installments', methods=['GET'])
def get_installments():
    """Obtener todas las cuotas (público) - estructura para checkout"""
    try:
        db.session.rollback()
        
        only_active = request.args.get('only_active', 'true').lower() == 'true'
        
        # Obtener todos los tipos de tarjeta activos
        card_types_query = CardType.query
        if only_active:
            card_types_query = card_types_query.filter_by(is_active=True)
        card_types = card_types_query.order_by(CardType.display_order, CardType.name).all()
        
        # Construir la estructura para el checkout
        result = {}
        
        for card_type in card_types:
            # Obtener installments para este tipo de tarjeta
            installments_query = CardBankInstallment.query.filter_by(card_type_id=card_type.id)
            if only_active:
                installments_query = installments_query.filter_by(is_active=True)
            installments = installments_query.all()
            
            # Agrupar por banco
            banks_data = {}
            for inst in installments:
                bank = Bank.query.get(inst.bank_id)
                if not bank or (only_active and not bank.is_active):
                    continue
                
                bank_name = bank.name
                if bank_name not in banks_data:
                    banks_data[bank_name] = []
                
                banks_data[bank_name].append({
                    'cuotas': inst.installments,
                    'recargoPorcentaje': float(inst.surcharge_percentage)
                })
            
            if banks_data:
                result[card_type.code] = banks_data
        
        return jsonify({
            'success': True,
            'data': result
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@card_banks_bp.route('/admin/card-bank-installments', methods=['POST'])
@admin_required
def create_installment():
    """Crear una nueva cuota (admin)"""
    try:
        data = request.get_json()
        
        if not data or not data.get('card_type_id') or not data.get('bank_id') or not data.get('installments'):
            return jsonify({
                'success': False,
                'error': 'card_type_id, bank_id e installments son requeridos'
            }), 400
        
        installment = CardBankInstallment(
            card_type_id=uuid.UUID(data['card_type_id']),
            bank_id=uuid.UUID(data['bank_id']),
            installments=data['installments'],
            surcharge_percentage=data.get('surcharge_percentage', 0),
            is_active=data.get('is_active', True),
            display_order=data.get('display_order', 0)
        )
        
        db.session.add(installment)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': installment.to_dict(include_card_type=True, include_bank=True)
        }), 201
    except IntegrityError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Ya existe una cuota con esa combinación de tarjeta, banco y número de cuotas'
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@card_banks_bp.route('/admin/card-bank-installments/<uuid:installment_id>', methods=['PUT'])
@admin_required
def update_installment(installment_id):
    """Actualizar una cuota (admin)"""
    try:
        installment = CardBankInstallment.query.get_or_404(installment_id)
        data = request.get_json()
        
        if 'installments' in data:
            installment.installments = data['installments']
        if 'surcharge_percentage' in data:
            installment.surcharge_percentage = data['surcharge_percentage']
        if 'is_active' in data:
            installment.is_active = data['is_active']
        if 'display_order' in data:
            installment.display_order = data['display_order']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': installment.to_dict(include_card_type=True, include_bank=True)
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@card_banks_bp.route('/admin/card-bank-installments/<uuid:installment_id>', methods=['DELETE'])
@admin_required
def delete_installment(installment_id):
    """Eliminar una cuota (admin)"""
    try:
        installment = CardBankInstallment.query.get_or_404(installment_id)
        db.session.delete(installment)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Cuota eliminada correctamente'
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@card_banks_bp.route('/admin/card-bank-installments', methods=['GET'])
@admin_required
def get_all_installments_admin():
    """Obtener todas las cuotas con detalles (admin)"""
    try:
        db.session.rollback()
        
        card_type_id = request.args.get('card_type_id')
        bank_id = request.args.get('bank_id')
        
        query = CardBankInstallment.query
        
        if card_type_id:
            query = query.filter_by(card_type_id=uuid.UUID(card_type_id))
        if bank_id:
            query = query.filter_by(bank_id=uuid.UUID(bank_id))
        
        installments = query.order_by(
            CardBankInstallment.card_type_id,
            CardBankInstallment.bank_id,
            CardBankInstallment.display_order,
            CardBankInstallment.installments
        ).all()
        
        return jsonify({
            'success': True,
            'data': [inst.to_dict(include_card_type=True, include_bank=True) for inst in installments]
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
