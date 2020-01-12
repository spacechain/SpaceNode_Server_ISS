from flask import render_template, request, current_app
from app.main import main
from app.main.forms import OTPForm, SecretForm, InitForm
from flask_login import login_required
from app.models import TransactionRecord, ServerInfo
from app import db
from crontab.pack import send_file
from crontab.unpack_certificate import init_server
from datetime import datetime, timedelta
from app.tools import ftp_upload
from app.tools import get_logger
import qrcode
import constants

logger = get_logger(__name__)


@main.before_request
def create_before_request():
    if request.method == 'GET':
        logger.info(request.args)
    elif request.method == 'POST':
        logger.info(request.form)


@main.route('/')
@login_required
def home():
    return render_template('base.html')


@main.route('/index')
@login_required
def index():
    return render_template('base.html')


@main.route('/cancel_delay/<id>', methods=['GET'])
def cancel_delay(id):
    transaction = TransactionRecord.query.filter_by(id=id).first()
    transaction.delayed_type = constants.WALLET_TYPE_NOT_DELAYED
    db.session.add(transaction)
    db.session.commit()
    return render_template('cancel_delay.html', msg='yes')


@main.route('/cancel_sign/<id>', methods=['GET'])
def cancel_sign(id):
    transaction = TransactionRecord.query.filter_by(id=id).first()
    transaction.state = constants.TRANSACTION_STATE_CANCELLED
    db.session.add(transaction)
    db.session.commit()
    return render_template('cancel_delay.html', msg='yes')


@main.route('/get_secret_key', methods=['GET', 'POST'])
@login_required
def get_secret_key():
    form = SecretForm()

    server_info = ServerInfo.query.filter_by(state=constants.SERVER_ENABLE).first()
    secret_key = server_info.secret_key

    if form.validate_on_submit():
        server_info.secret_key = None
        db.session.add(server_info)
        db.session.commit()
        return render_template('base.html', m='SERVER DEL')

    if secret_key:
        logger.info('================secret_key================ %s' % str(type(secret_key)))
        logger.info('================secret_key================ %s' % secret_key)
        uri = "otpauth://hotp/%s?secret= %s" % ('探诚科技', secret_key)
        logger.info('================uri================ %s' % uri)

        img = qrcode.make(uri)
        img.save(current_app.config['SECRET_PNG_PATH'])

        return render_template('get_secret_key.html', secret_key=secret_key, form=form)

    else:
        return render_template('base.html', m="Didn't have a key")


@main.route('/pack_file', methods=['POST', 'GET'])
@login_required
def pack_file():
    """
    压缩文件
    :return:
    """
    form = OTPForm()
    befor_24 = datetime.utcnow() - timedelta(hours=constants.DELAYED_PERIOD)

    filter_by_dont_delay = '''(state =%s and delayed_type =%s )''' % (
        constants.TRANSACTION_STATE_WAITING, constants.WALLET_TYPE_NOT_DELAYED)

    filter_by_delay = '''(state = %s and delayed_type = %s and created_at <= '%s') ''' % (
        constants.TRANSACTION_STATE_WAITING, constants.WALLET_TYPE_DELAYED, befor_24)

    sql_str = '''select * from transaction_records where ''' + filter_by_dont_delay + ''' or ''' +\
              filter_by_delay + ''' order by  transaction_records.created_at  limit %s ''' % constants.PACK_NUM

    data_query = db.session.execute(sql_str)

    server_info = ServerInfo.query.filter_by(state=constants.SERVER_ENABLE).first()
    secret_id = server_info.sat_index

    if not data_query.fetchall():
        return render_template('base.html', m='No compression required')

    if form.validate_on_submit():
        otp = form.otp.data

        try:
            f_name = send_file(otp, logger, int(secret_id))
            ftp_upload(f_name)
        except Exception as e:
            logger.info('===============================================pack error %s' % str(e))
            return render_template('base.html', m=str(e))

        return render_template('base.html', m='Wait for satellite return')

    return render_template('pack_file.html', form=form)


@main.route('/initialize_server', methods=['POST', 'GET'])
@login_required
def initialize_server():
    form = InitForm()

    if form.validate_on_submit():

        try:
            if init_server(logger) is False:
                return render_template('base.html', m='Failure  initialization')

        except Exception as e:
            logger.info('===============================================pack error %s' % str(e))
            return render_template('base.html', m=str(e))

        return render_template('base.html', m='Successful initialization')

    return render_template('init_server.html', form=form)
