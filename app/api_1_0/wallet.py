# -*- coding:utf-8 -*-
from app.api_1_0 import api_1_0
from app import db
from app.models import Wallet, SatXpub
from flask_restful.reqparse import RequestParser
from flask import jsonify, request
from app.tools import get_logger, re_email
import json
from bip32 import constants
from flask import current_app
import constants as tc_constants

parser = RequestParser()

logger = get_logger(__name__)


@api_1_0.before_request
def create_logging():
    if request.method == 'GET':
        logger.info(request.args)
    elif request.method == 'POST':
        logger.info(request.json)


@api_1_0.route('/create_wallet', methods=['post'])
def create_wallet():
    """
    创建钱包
    :return:
    """
    req = request.data.decode()
    req = json.loads(req)

    email = req.get('email_address')
    first_xpub = req.get('first_xpub')
    secondary_xpub = req.get('secondary_xpub')
    is_test = req.get('is_test', None)
    type_of_service = req.get('type_of_service')

    if not email \
            or not first_xpub \
            or not secondary_xpub \
            or is_test is None \
            or is_test not in [tc_constants.BITCOIN_MAIN, tc_constants.BITCOIN_TEST] \
            or type_of_service not in ['personal', 'enterprise']:
        logger.info('==========invalid args==========%s' % str(req))
        return jsonify({'message': 'email error', "status": 400, }), 400

    is_test = is_test

    if not re_email(email):
        logger.info('==========email error==========%s' % str(email))
        return jsonify({'message': 'email error', "status": 400, }), 400

    # 分配卫星公钥 私钥
    if not is_test:
        wallet_xpub = current_app.config['FEE_XPUB']
        sat_info = SatXpub.query.filter_by(is_testnet=tc_constants.BITCOIN_MAIN).first()
        constants.set_mainnet()
    else:
        wallet_xpub = current_app.config['FEE_XPUB_BY_TESTNET']
        constants.set_testnet()
        sat_info = SatXpub.query.filter_by(is_testnet=tc_constants.BITCOIN_TEST).first()

    sat_xpub = sat_info.xpub

    long_id, short_id = Wallet.get_user_id(first_xpub, secondary_xpub)

    # 生成收费钱包子地址
    try:
        legacy_address, segwit_address = Wallet.make_billing_address(long_id, wallet_xpub, 1)
    except:
        logger.info('===================get((legacy_address,segwit_address))error===================')
        return jsonify({"status": 400,
                        'message': 'error'}), 400

    wallet = Wallet(email=email, first_xpub=first_xpub, secondary_xpub=secondary_xpub, sat_xpub_id=sat_info.id,
                    short_id=short_id, is_testnet=is_test, segwit_address=segwit_address,
                    legacy_address=legacy_address, type_of_service=type_of_service)

    db.session.add(wallet)
    db.session.commit()
    # 随意交换下字符串顺序 客户端再拼装
    otp_secret_key = wallet.otp_secret_key[5:] + wallet.otp_secret_key[:5]
    sat_xpub = sat_xpub[5:] + sat_xpub[:5]
    return jsonify({
        'otp_secret': otp_secret_key,
        'sat_xpub': sat_xpub
    })
