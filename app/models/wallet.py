from app import db
from app.models.tools import get_uuid, get_secret_key
from datetime import datetime
from bip32.bip32 import BIP32Node
from bip32 import ecc
from bip32 import bip32, bitcoin
from typing import Union
import hashlib
import constants


class Wallet(db.Model):
    """
    payment_id 在即将广播的交易信息中
    可能存在 在发送至地面站之前 做了二百笔交易
    """
    __tablename__ = 'wallets'

    id = db.Column(db.String(32), default=get_uuid, primary_key=True, nullable=False, index=True, unique=True)

    email = db.Column(db.String(32), nullable=False)

    # 个人 企业 企业延时24小时发送卫星
    type_of_service = db.Column(db.String(32), nullable=False)

    transaction_records = db.relationship('TransactionRecord', backref='wallet')

    first_xpub = db.Column(db.String(128), nullable=False)
    secondary_xpub = db.Column(db.String(128), nullable=False)

    sat_xpub_id = db.Column(db.String(32), db.ForeignKey('sat_xpub.id'))

    # in trustedcoin ID
    short_id = db.Column(db.String(128), nullable=False)

    # google one time password
    otp_secret_key = db.Column(db.String(32), nullable=False, default=get_secret_key)
    # google one time password
    otp_index = db.Column(db.Integer(), nullable=False, default=1)

    # 是否为测试网络，是：1 否：0
    is_testnet = db.Column(db.Integer(), nullable=False, default=0)

    # 剩余交易次数 首次创建为 0
    #
    # 卫星签名前，若>=0则给签名，并且数据库-1，当等于-1时禁止签名
    #
    # 卫星签名并且服务器广播成功后，判断是否<=0，是则获取是否交小费，交了置为20，否则略过
    tx_remaining = db.Column(db.Integer(), nullable=False, default=0)

    legacy_address = db.Column(db.String(128), nullable=False)
    segwit_address = db.Column(db.String(128), nullable=False)

    state = db.Column(db.Integer, default=constants.WALLET_ENABLE, nullable=False)

    # created_at = db.Column(db.TIMESTAMP, default=datetime.utcnow, nullable=False)
    # updated_at = db.Column(db.TIMESTAMP, default=datetime.utcnow, nullable=False, onupdate=datetime.utcnow)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, onupdate=datetime.utcnow)

    @staticmethod
    def make_billing_address(long_id, wallet_xpub, num):
        """
        根据公钥 获取子地址
        :param long_id:
        :param wallet_xpub:
        :param num:
        :return:
        """
        xpub = Wallet.make_xpub(wallet_xpub, long_id)
        usernode = BIP32Node.from_xkey(xpub)
        child_node = usernode.subkey_at_public_derivation([num])
        pubkey = child_node.eckey.get_public_key_bytes(compressed=True)
        return bitcoin.public_key_to_p2pkh(pubkey), bitcoin.public_key_to_p2wpkh(pubkey)

    @staticmethod
    def make_xpub(xpub, s) -> str:
        rootnode = BIP32Node.from_xkey(xpub)
        child_pubkey, child_chaincode = bip32._CKD_pub(
            parent_pubkey=rootnode.eckey.get_public_key_bytes(compressed=True),
            parent_chaincode=rootnode.chaincode,
            child_index=s)
        child_node = BIP32Node(xtype=rootnode.xtype,
                               eckey=ecc.ECPubkey(child_pubkey),
                               chaincode=child_chaincode)
        return child_node.to_xpub()

    @staticmethod
    def get_user_id(xpub1, xpub2):
        """
        根据公钥一二获得short long id
        :param xpub1:
        :param xpub2:
        :return:
        """

        def make_long_id(xpub_hot, xpub_cold):
            return Wallet.sha256(''.join(sorted([xpub_hot, xpub_cold])))

        # 二进制 long_id: b"\x1e\x11-'\xbf\xb45\x0e;;\xc9-\x84\xb6\x84XD_\xbbK\xc4u\x1b\xbf\xac\x13\xfd\x18\xf2WX,"
        long_id = make_long_id(xpub1, xpub2)

        # 返回摘要，作为十六进制数据字符串值 2ac74a10ba47c9e942d97bb06c58eadf73daba5fb741e3888da0e711fb1b2c82
        short_id = hashlib.sha256(long_id).hexdigest()
        return long_id, short_id

    @staticmethod
    def sha256(x: Union[bytes, str]) -> bytes:
        x = Wallet.to_bytes(x, 'utf8')
        return bytes(hashlib.sha256(x).digest())

    @staticmethod
    def to_bytes(something, encoding='utf8') -> bytes:
        """
        cast string to bytes() like object, but for python2 support it's bytearray copy
        """
        if isinstance(something, bytes):
            return something
        if isinstance(something, str):
            return something.encode(encoding)
        elif isinstance(something, bytearray):
            return bytes(something)
        else:
            raise TypeError("Not a string or bytes like object")
