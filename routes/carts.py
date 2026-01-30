from flask import Blueprint, request, jsonify
from database import db
from models.cart import Cart
from routes.auth import user_required
from sqlalchemy.exc import IntegrityError

carts_bp = Blueprint('carts', __name__)

@carts_bp.route('', methods=['POST'])
@user_required
def create_cart():
    """
    Crea un carrito para el usuario autenticado si no existe uno
    Solo se crea si el usuario no tiene ningún carrito previo
    """
    try:
        user = request.user
        
        # Verificar si el usuario ya tiene un carrito
        existing_cart = Cart.query.filter_by(user_id=user.id).first()
        
        if existing_cart:
            # Si ya existe, retornar el existente
            return jsonify({
                'success': True,
                'data': existing_cart.to_dict(),
                'message': 'Carrito ya existe'
            }), 200
        
        # Crear nuevo carrito
        cart = Cart(
            user_id=user.id
        )
        
        db.session.add(cart)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': cart.to_dict(),
            'message': 'Carrito creado exitosamente'
        }), 201
        
    except IntegrityError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Error de integridad al crear el carrito'
        }), 400
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error en create_cart: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@carts_bp.route('', methods=['GET'])
@user_required
def get_user_cart():
    """
    Obtiene el carrito del usuario autenticado si existe
    """
    try:
        user = request.user
        
        cart = Cart.query.filter_by(user_id=user.id).first()
        
        if not cart:
            return jsonify({
                'success': True,
                'data': None,
                'message': 'El usuario no tiene carrito'
            }), 200
        
        return jsonify({
            'success': True,
            'data': cart.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error en get_user_cart: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@carts_bp.route('', methods=['DELETE'])
@user_required
def delete_cart():
    """
    Elimina el carrito del usuario autenticado
    """
    try:
        user = request.user
        
        cart = Cart.query.filter_by(user_id=user.id).first()
        
        if not cart:
            return jsonify({
                'success': True,
                'message': 'El usuario no tiene carrito para eliminar'
            }), 200
        
        db.session.delete(cart)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Carrito eliminado exitosamente'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error en delete_cart: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
