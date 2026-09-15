from flask import Blueprint, request, jsonify
from database import db
from sqlalchemy import text
from datetime import datetime, timedelta
from models.whatsapp_click import WhatsappClick
from routes.admin_auth import admin_required

whatsapp_clicks_bp = Blueprint('whatsapp_clicks', __name__)

VALID_CLICK_TYPES = {'contact', 'checkout'}


@whatsapp_clicks_bp.route('/track/whatsapp-click', methods=['POST'])
def track_whatsapp_click():
    """
    Registra un click en un botón/flujo de WhatsApp (sin autenticación, llamado desde el storefront).
    Body: { "type": "contact" | "checkout", "page": "/ruta-opcional" }
    """
    try:
        data = request.get_json(silent=True) or {}
        click_type = data.get('type')

        if click_type not in VALID_CLICK_TYPES:
            return jsonify({'success': False, 'error': 'Invalid type'}), 400

        page = data.get('page')
        page = str(page)[:255] if page else None

        click = WhatsappClick(click_type=click_type, page=page)
        db.session.add(click)
        db.session.commit()

        return jsonify({'success': True}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@whatsapp_clicks_bp.route('/admin/metrics/whatsapp-clicks', methods=['GET'])
@admin_required
def get_whatsapp_click_metrics():
    """
    Cuenta de clicks a WhatsApp, divididos por tipo.
    Parámetros opcionales: start_date, end_date (formato YYYY-MM-DD)
    """
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        date_filter = ""
        params = {}
        if start_date:
            date_filter += " AND created_at >= :start_date"
            params['start_date'] = start_date
        if end_date:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
            end_date_next = (end_date_obj + timedelta(days=1)).strftime('%Y-%m-%d')
            date_filter += " AND created_at < :end_date_next"
            params['end_date_next'] = end_date_next

        query = text(f"""
            SELECT click_type, COUNT(*) as count
            FROM whatsapp_clicks
            WHERE 1=1 {date_filter}
            GROUP BY click_type
        """)
        result = db.session.execute(query, params)

        counts = {'contact': 0, 'checkout': 0}
        for row in result:
            if row.click_type in counts:
                counts[row.click_type] = row.count

        return jsonify({
            'success': True,
            'data': {
                'contact_clicks': counts['contact'],
                'checkout_clicks': counts['checkout'],
                'total_clicks': counts['contact'] + counts['checkout'],
            }
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
