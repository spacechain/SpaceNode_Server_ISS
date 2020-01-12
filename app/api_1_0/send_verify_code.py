# -*- coding:utf-8 -*-
from app.api_1_0 import api_1_0
from flask import jsonify, request
from app.models import User, Wallet, AuthVerifyCode
from flask_restful.reqparse import RequestParser
from app.tools import get_logger

parser = RequestParser()

logger = get_logger(__name__)


@api_1_0.before_request
def create_logging():
    if request.method == 'GET':
        logger.info(request.args)
    elif request.method == 'POST':
        logger.info(request.form)


@api_1_0.route('/send_code_by_email/', methods=['post'])
def send_code_by_email():
    parser.add_argument('email', type=str, required=True, nullable=False, location=['form'])

    req = parser.parse_args(strict=True)
    email = req.get('email')
    rsp = {
        'succeed': True,
        'error_message': ''
    }

    if not AuthVerifyCode.re_email(email):
        rsp = {
            'succeed': False,
            'error_message': 'email type error'
        }
        return jsonify(rsp), 400

    AuthVerifyCode.send_code_thr(email)

    return jsonify(rsp)


@api_1_0.route('/send_code_by_wallet')
def send_code_by_wallet():
    rsp = {
        'succeed': True,
        'error_message': ''
    }

    parser.add_argument('email', type=str, required=True, nullable=False, location=['args'])
    parser.add_argument('wallet_id', type=str, required=False, nullable=True, location=['args'])

    req = parser.parse_args(strict=True)
    email = req.get('email')
    wallet_id = req.get('wallet_id')

    if not Wallet.query.filter_by(id=wallet_id).first():
        return jsonify('wallet not found')

    if not User.query.filter_by(email=email).first():
        return jsonify({'email not found'})

    if not AuthVerifyCode.re_email(email):
        rsp = {
            'succeed': False,
            'error_message': 'email type error'
        }
        return jsonify(rsp), 400

    AuthVerifyCode.send_code_thr(email)

    return jsonify(rsp)
