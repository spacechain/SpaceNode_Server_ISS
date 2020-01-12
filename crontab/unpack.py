# -*- coding:utf-8 -*-
from struct import *
import ftplib
import uuid
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import sys
import os
import requests
from bs4 import BeautifulSoup
import logging
import time

p_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

sys.path.append(r'%s' % str(p_dir))
from config import config
import constants

# 初始化数据库连接:
engine = create_engine(config['default'].SQLALCHEMY_DATABASE_URI)
DBSession = sessionmaker(bind=engine)
session = DBSession()

# FTP
ftp_ip = config['default'].FTP_IP
ftp_user = config['default'].FTP_USER
ftp_pwd = config['default'].FTP_PWD
ftp_path = config['default'].FTP_DOWNLOAD_PATH

# 下载下来的文件存储路径
file_local_path = config['default'].DOWNLOAD_FILE_PATH

# LOG
LOG_LEVEL = logging.DEBUG
LOG_FILEMODE = 'a'
LOG_FILE_PATH = '/home/tc/server_log/unpack.log'
LOG_FORMAT = '%(asctime)s - %(pathname)s[line:%(lineno)d] - %(levelname)s: %(message)s'
logging.basicConfig(level=LOG_LEVEL, filename=LOG_FILE_PATH, filemode=LOG_FILEMODE, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


def get_fee(payment_id, wallet_addr):
    """
    获取缴费记录
    :param payment_id:
    :param wallet_addr:
    :return:        :return:
    """
    payment_id = payment_id.strip()
    if '\n' in payment_id:
        payment_id = payment_id.replace('\n', '')
    url = 'https://tbtc.bitaps.com/%s' % payment_id
    logger.info('---------------------------')
    logger.info('-----py------%s----------------' % payment_id)
    logger.info('-----url------%s----------------' % url)
    time.sleep(20)
    req = requests.get(url)
    soup = BeautifulSoup(req.text, "html.parser")

    res = str(soup.find_all(id="tx-outputs")[0])
    logger.info('-----res------%s----------------' % str(res))

    soup2 = BeautifulSoup(res, "html.parser")

    res2 = soup2.find_all("td")

    fee_index = None
    texts = []

    for i in res2:
        texts.append(i.get_text())
        if wallet_addr in str(i):
            logger.info('==================')
            fee_index = res2.index(i) + 1

    fee = texts[fee_index]
    logger.info('-----fee------%s----------------' % str(fee))

    if '\n' in fee:
        fee = fee.replace('\n', '')
    logger.info('=========================float(fee)%s' % fee)
    return float(fee)


def check_file_name(names):
    """
    剔除已经下载过的文件

    :param names:
    :return:
    """
    logger.info('================== check_file_name =================')

    sql_str = """select file_names from pull_records where state = %s or state = %s""" % (
        constants.PULL_STATE_SUCCESS, constants.PULL_STATE_UNPACK_SUCCESS)

    data_query = session.execute(sql_str)
    session.close()

    resuls = []

    for i in names:
        if i[-4:] == '.res':
            resuls.append(i)

    for record in data_query.fetchall():

        if record.file_names in resuls:
            resuls.remove(record.file_names)

    # todo 数据库里没有该交易 则剔除

    return resuls


def ftp_download():
    """
    ftp下载文件
    :return:
    """
    logger.info('================== sign in ftp=================')

    f = ftplib.FTP(ftp_ip)  # 实例化FTP对象
    f.login(ftp_user, ftp_pwd)  # 登录
    # 总是提示链接超时
    f.set_pasv(True)
    # 获取当前路径
    pwd_path = f.pwd()
    f.cwd(ftp_path)
    logger.info('================== ftp_path =================%s' % ftp_path)

    file_list = f.nlst()
    if not file_list:
        logger.info('================== not found files =================')
        return

    file_list = check_file_name(file_list)

    if not file_list:
        session.close()
        logger.info('================== not found files =================')

    # 每次只下载一个签名文件
    file_name = file_list[0]

    bufsize = 1024  # 设置缓冲器大小
    fp = open(file_local_path + file_name, 'wb')
    f.retrbinary('RETR %s' % file_name, fp.write)
    fp.close()
    f.quit()

    new_id = uuid.uuid4().hex

    sql_str = '''insert into pull_records(id,state,file_names,created_at,updated_at) values ('%s',%s,'%s','%s','%s')''' % (
        new_id, constants.PULL_STATE_SUCCESS, file_name, datetime.utcnow(), datetime.utcnow())
    data_query = session.execute(sql_str)
    session.commit()
    logger.info('==================insert pull_records ======new_id===========%s' % new_id)

    results = []
    try:
        results, state = unpack_file(file_local_path + file_name)

        update_sql_str = """ update pull_records set state = %s where id = '%s' """ % (state, str(new_id))
    except:
        update_sql_str = """ update pull_records set state = %s where id = '%s' """ % (
            constants.PULL_STATE_UNPACK_FAIL, str(new_id))

    data_query = session.execute(update_sql_str)

    session.commit()
    return results


def get_tx_item(tx):
    """
    拆解每一个tx文件
    :param tx:
    :return:
    """
    tx_id = tx[0:32]
    tx_res_length = tx[32:36]

    tx_res_length = unpack('i', tx_res_length)

    # tx_res_data的长度
    tx_res_length = tx_res_length[0]

    # 板子签名失败
    if tx_res_length == 0:
        hex_data = None
    else:
        tx_res_data = tx[36:36 + tx_res_length]

        hex_data_len = tx_res_data[1:3]

        hex_data_len = unpack('H', hex_data_len)[0]

        hex_data = tx_res_data[3:3 + hex_data_len]

        hex_data = str(hex_data.hex())

    item_last_index = 36 + tx_res_length

    return tx_id, hex_data, item_last_index


def unpack_file(file_name):
    """
    解压文件
    :param file_name:
    :return:
    """

    logger.info('================== unpack_file =================')

    f = open(file_name, "rb")
    f = f.read()

    server_id = f[0:4]
    server_id = unpack('i', server_id)[0]
    logger.info('================== server_id =================%s' % server_id)

    # 校验server_id
    sql_str = """select sat_index from server_info where state =%s""" % constants.SERVER_ENABLE
    data_query = session.execute(sql_str)
    # todo 没有serverinfo 退出
    server_info = data_query.fetchall()[0]
    session.commit()
    if server_info.sat_index != server_id:
        logger.info('================== server_id error =================%s' % server_id)
        return None, constants.PULL_STATE_SERVER_ERROR

    tx_length = f[4:12]
    tx_length = unpack('q', tx_length)[0]

    tx_res_num = f[12:16]
    tx_res_num = unpack('i', tx_res_num)[0]

    # otp 验证失败 则每笔交易的长度为36
    if tx_res_num * 36 == tx_length:
        return None, constants.PULL_STATE_OTP_FAIL

    tx_list = f[16:16 + tx_length]

    results = []

    while True:

        if tx_list:
            tx_id, hex_data, item_last_index = get_tx_item(tx_list)

            results.append({
                'tx_id': tx_id,
                'hex': hex_data
            })
            tx_list = tx_list[item_last_index:]
        else:
            break
    return results, constants.PULL_STATE_UNPACK_SUCCESS


def get_wallet_by_tx(tx_id):
    """
    根据交易ID查找对应钱包
    :param tx_id:
    :return:
    """
    find_tx_sql_str = """ select wallet_id from transaction_records where id = '%s' """ % (tx_id)

    data_query = session.execute(find_tx_sql_str)
    if not data_query:
        return
    wallet_id = data_query.fetchall()[0].wallet_id
    session.commit()

    find_wallet_sql_str = """ select * from wallets where id = '%s' """ % (wallet_id)

    data_query = session.execute(find_wallet_sql_str)

    wallet_info = data_query.fetchall()[0]
    session.commit()
    return wallet_info


if __name__ == '__main__':
    results = ftp_download()

    if not results:
        exit()

    for tx_item in results:

        hex_str = tx_item['hex']
        tx_id = tx_item['tx_id'].decode()

        # 获取钱包信息
        wallet_info = get_wallet_by_tx(tx_id)
        if not wallet_info:
            continue

        # 卫星签名失败
        if hex_str is None:
            # 修改交易状态为 签名失败
            logger.info('================== sign error =================')
            update_sql_str = """ update transaction_records set state = %s where id = '%s' """ % (
                constants.TRANSACTION_STATE_SIGN_FAIL, tx_id)
            data_query = session.execute(update_sql_str)
            session.commit()

            # 修改交易对应的钱包 剩余交易次数
            tx_remaining = wallet_info.tx_remaining + 1
            update_sql_str = """ update wallet set tx_remaining = %s where id = '%s' """ % (
                tx_remaining, wallet_info.id)
            data_query = session.execute(update_sql_str)
            session.commit()
            logger.info('================== sign error ,change tx_remaining =================')

            # todo 发送邮件
            continue

        broadcast_shell_str = '/home/tc/Electrum-3.3.8/run_electrum broadcast %s' % hex_str

        try:
            logger.info('================== hex_str ========%s=========' % hex_str)

            payment_id = os.popen(broadcast_shell_str).read()
            logger.info('================== payment_id ========%s=========' % payment_id)
        except Exception as e:
            # 广播失败
            logger.info('================== broadcast error =================')
            update_sql_str = """ update transaction_records set state = % where id = '%s' """ % (
                constants.TRANSACTION_STATE_BROADCAST_FAIL, tx_id)
            data_query = session.execute(update_sql_str)
            session.commit()

        else:

            # 广播成功
            update_sql_str = """ update transaction_records set signed_tx_hex = '%s' ,state = %d where id = '%s' """ % (
                hex_str, constants.TRANSACTION_STATE_BROADCAST_SUCCESS, tx_id)
            data_query = session.execute(update_sql_str)
            session.commit()
            logger.info('================== broadcast down =================')

            # 修改钱包交易次数
            if wallet_info.tx_remaining < 0:
                fee = get_fee(payment_id, wallet_info.segwit_address)
                logger.info('================== fee %s =================' % fee)

                logger.info('================== feeadsfsdafasdfasdfs =================')
                if fee == constants.FEE:
                    tx_remaining = wallet_info.tx_remaining + constants.INITIAL_RESIDUAL_NUMBER
                    update_sql_str = """ update wallets set tx_remaining = %s where id = '%s' """ % (
                        tx_remaining, wallet_info.id)
                    data_query = session.execute(update_sql_str)
                    session.commit()
                    logger.info('================== change tx_remaining =================')
