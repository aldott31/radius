# -*- coding: utf-8 -*-
import os
import socket
import struct
import hashlib
import logging

_logger = logging.getLogger(__name__)

RADIUS_CODE = {
    1: 'Access-Request',
    2: 'Access-Accept',
    3: 'Access-Reject',
    11: 'Access-Challenge',
}

ATTR = {
    'User-Name': 1,
    'User-Password': 2,
    'CHAP-Password': 3,
    'NAS-IP-Address': 4,
    'Reply-Message': 18,
    'CHAP-Challenge': 60,
}

class RadiusClient:
    def __init__(self, host, secret, auth_port=1812, timeout=2.0, retries=1):
        self.host = host
        self.secret = secret.encode('utf-8') if isinstance(secret, str) else secret
        self.port = int(auth_port or 1812)
        self.timeout = float(timeout or 2.0)
        self.retries = int(retries or 1)

    # -------- PAP ----------
    def access_request_pap(self, username, password, extra_attrs=None):
        req_auth = os.urandom(16)
        attrs = []
        attrs.append(self._pack_attr(ATTR['User-Name'], username.encode('utf-8')))
        enc_pwd = self._encode_user_password(password.encode('utf-8'), req_auth)
        attrs.append(self._pack_attr(ATTR['User-Password'], enc_pwd))
        if extra_attrs:
            attrs += self._pack_extra(extra_attrs)
        return self._send_request(1, req_auth, b''.join(attrs))

    # -------- CHAP ----------
    def access_request_chap(self, username, password, extra_attrs=None):
        # CHAP needs: CHAP-Challenge + CHAP-Password (1-byte chap_ident + 16-byte MD5)
        req_auth = os.urandom(16)
        chap_ident = os.urandom(1)  # 1 byte
        chap_chal = os.urandom(16)
        md = hashlib.md5(chap_ident + password.encode('utf-8') + chap_chal).digest()
        chap_value = chap_ident + md  # 17 bytes

        attrs = []
        attrs.append(self._pack_attr(ATTR['User-Name'], username.encode('utf-8')))
        attrs.append(self._pack_attr(ATTR['CHAP-Password'], chap_value))
        attrs.append(self._pack_attr(ATTR['CHAP-Challenge'], chap_chal))
        if extra_attrs:
            attrs += self._pack_extra(extra_attrs)
        return self._send_request(1, req_auth, b''.join(attrs))

    # ------------- internals ---------------
    def _encode_user_password(self, password_bytes, req_auth):
        # RFC2865 §5.2
        p = password_bytes
        if len(p) % 16 != 0:
            p = p + b'\x00' * (16 - (len(p) % 16))
        result = b''
        last = req_auth
        for i in range(0, len(p), 16):
            b16 = p[i:i+16]
            md = hashlib.md5(self.secret + last).digest()
            c = bytes(a ^ b for a, b in zip(b16, md))
            result += c
            last = c
        return result

    def _pack_attr(self, t, vbytes):
        if not isinstance(vbytes, (bytes, bytearray)):
            vbytes = bytes(vbytes)
        l = 2 + len(vbytes)
        if l > 255:
            raise ValueError("Attribute too long")
        return struct.pack("!BB", t, l) + vbytes

    def _pack_request(self, code, ident, req_auth, attrs):
        length = 20 + len(attrs)
        return struct.pack("!BBH16s", code, ident, length, req_auth) + attrs

    def _verify_response_auth(self, resp, req_auth):
        # Resp: Code(1),ID(1),Len(2),Authenticator(16),Attrs...
        code, ident, length = struct.unpack("!BBH", resp[:4])
        resp_auth = resp[4:20]
        attrs = resp[20:length]
        # RFC2865 §3: ResponseAuth = MD5(Code+ID+Length+RequestAuth+Attributes+secret)
        md = hashlib.md5()
        md.update(struct.pack("!BBH", code, ident, length))
        md.update(req_auth)
        md.update(attrs)
        md.update(self.secret)
        calc = md.digest()
        return resp_auth == calc

    def _parse_reply_message(self, resp):
        try:
            _, _, length = struct.unpack("!BBH", resp[:4])
            pos = 20
            out = []
            while pos < length:
                t = resp[pos]
                l = resp[pos+1]
                v = resp[pos+2:pos+l]
                if t == ATTR['Reply-Message']:
                    try:
                        out.append(v.decode('utf-8', 'ignore'))
                    except Exception:
                        pass
                pos += l
            return "\n".join(out).strip()
        except Exception:
            return ""

    def _send_request(self, code, req_auth, attrs):
        ident = os.urandom(1)[0]
        packet = self._pack_request(code, ident, req_auth, attrs)

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(self.timeout)
        last_err = None
        local_ip = None

        # Lidhemi që të dimë IP-në e burimit (src) që do përdorë socket-i
        try:
            s.connect((self.host, self.port))
            local_ip = s.getsockname()[0]
        except Exception:
            # do të kalohet te sendto më poshtë
            pass

        for _ in range(max(1, self.retries)):
            try:
                if local_ip:
                    s.send(packet)
                else:
                    s.sendto(packet, (self.host, self.port))

                resp, _ = s.recvfrom(4096)
                if len(resp) < 20:
                    raise ValueError("Short RADIUS response")
                rcode = resp[0]
                # verify response authenticator
                if not self._verify_response_auth(resp, req_auth):
                    raise ValueError(f"Response Authenticator mismatch (src={local_ip})")
                msg = self._parse_reply_message(resp)
                ok = (rcode == 2)
                result = {
                    'ok': ok,
                    'code': RADIUS_CODE.get(rcode, str(rcode)),
                    'reply_message': msg,
                    'raw': resp[:],
                    'src_ip': local_ip,
                    'dst': f"{self.host}:{self.port}",
                }
                _logger.info("RADIUS %s (src=%s) -> %s; msg=%s",
                             RADIUS_CODE.get(code), local_ip, result['code'], msg)
                return result
            except Exception as e:
                last_err = e

        # në fund, nëse ka qenë timeout, kthe mesazh me src/dst për diag
        if isinstance(last_err, (TimeoutError, socket.timeout)) or last_err is None:
            raise TimeoutError(f"timed out (src={local_ip} → dst={self.host}:{self.port})")
        raise last_err

    def _pack_extra(self, extra_attrs):
        packed = []
        for key, val in (extra_attrs or {}).items():
            if isinstance(key, str) and key in ATTR:
                t = ATTR[key]
            elif isinstance(key, int):
                t = key
            else:
                _logger.debug("Skipping unknown attr %s", key)
                continue
            vbytes = val if isinstance(val, (bytes, bytearray)) else str(val).encode('utf-8')
            packed.append(self._pack_attr(t, vbytes))
        return packed
