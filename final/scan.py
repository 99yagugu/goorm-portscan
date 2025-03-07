# 수정사항
# servicename 출력하도록 수정하기
# 함수 이름 통합
# 443, 3389추가
# 중복 코드 병합 - ftp, ssh 통합/smtp, ldap 통합
# IMAP 시간 설정하기

import socket
import struct
import time
import uuid
import imaplib
import telnetlib
import ssl
from pysnmp.hlapi import *
from smbprotocol.connection import Connection
from scapy.all import sr, IP, TCP, UDP, ICMP, sr1

#SMTPS, HTTPS, LDAPS
def scan_ssl_port(ip, port):
    if port == 465:
        service_name = "SMTPS"
    elif port == 443:
        service_name = "HTTPS"
    elif port == 636:
        service_name = "LDAPS"
    else:
        service_name = "알 수 없는 서비스"

    response_data = {'service':service_name, 'port': port, 'state': 'closed'}
    if syn_scan(ip, port):
        try:
            context = ssl.create_default_context()
            with socket.create_connection((ip, port)) as sock:
                with context.wrap_socket(sock, server_hostname=ip) as ssock:
                    banner = ssock.recv(1024).decode('utf-8')
                    response_data.update({'state': 'open', 'banner': banner})
        except Exception as err:
            response_data.update({'state': 'closed or filtered', 'error': str(err)})
    else:
        response_data['state'] = 'closed or filtered'
    return response_data

#SMTP, LDAP
def scan_smtp_ldap_port(ip, port):
    if port == 25:
        service_name = "SMTP"
    elif port == 587:
        service_name = "SMTP"
    elif port == 389:
        service_name = "LDAP"
    else:
        service_name = "알 수 없는 서비스"

    response_data = {'service':service_name, 'port': port, 'state': 'closed', 'error': None}
    
    if syn_scan(ip, port):
        try:
            with socket.create_connection((ip,port), timeout=10) as connection:
               banner = connection.recv(1024).decode('utf-8')
               response_data.update({'state': 'open', 'banner': banner})
        except socket.error as err:
            response_data.update({'state': 'open but unable to receive banner', 'error': str(err)})
    else:
        response_data['state'] = 'closed or filtered'
    return response_data 

def syn_scan(ip, port):
    packet = IP(dst=ip)/TCP(dport=port, flags="S")
    # sr 함수는 (발송된 패킷, 받은 응답) 튜플의 리스트를 반환
    # 여기서는 받은 응답만 필요하므로, _ 를 사용해 발송된 패킷 부분을 무시
    ans, _ = sr(packet, timeout=2, verbose=0)  # ans는 받은 응답 리스트
    for sent, received in ans:
        if received and received.haslayer(TCP):
            if received[TCP].flags & 0x12:  # SYN-ACK 확인
                return True  # 포트열림
            elif received[TCP].flags & 0x14:  # RST-ACK 확인
                return False  # 포트 닫힘
    return False  # 응답없거나 다른에러

def scan_udp_port(host, port):
    #port = 520
    response_data = {
        'service': "UDP",
        'port': port,
        'state': 'open or filterd'
    }
    packet = IP(dst=host)/UDP(dport=port)
    response = sr1(packet, timeout=2, verbose=0)
    
    if response is None:
        response_data['error'] = 'No response (possibly open or filtered).'
    elif response.haslayer(ICMP):
        if int(response.getlayer(ICMP).type) == 3 and int(response.getlayer(ICMP).code) == 3:
            response_data['state'] = 'closed'
        else:
            response_data['error'] = f"ICMP message received (type: {response.getlayer(ICMP).type}, code: {response.getlayer(ICMP).code})"
    else:
        response_data['error'] = 'Received unexpected response.'
        
    return response_data


def scan_telnet_port(host, port):
    #port = 23
    response_data = {'serivce': "Telnet", 'port': port, 'state': 'closed'}
    
    try:
        tn = telnetlib.Telnet(host, port, timeout=5)  # Telnet 객체 생성 및 서버에 연결 (타임아웃 설정)
        banner = tn.read_until(b"\r\n", timeout=5).decode('utf-8').strip()  # 배너 정보 읽기
        tn.close()  # 연결 종료
        response_data['state'] = 'open'
        response_data['banner'] = banner
    except ConnectionRefusedError:
        response_data['error'] = '연결거부'
    except Exception as e:
        response_data['state'] = 'error'
        response_data['error'] = str(e)
    return response_data

def scan_dns_port(host, port):
    response_data = {'service':'DNS', 'port': port, 'state': 'closed'}
    try:
        # UDP 소켓 생성
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1)  # 타임아웃 설정

        # DNS 서버에 데이터 전송
        sock.sendto(b'', (host, port))

        # 데이터 수신 시 포트가 열려 있다고 가정
        # UDP 스캔은 응답이 없어도 포트가 열려 있다고 가정합니다.
        response_data['state'] = 'open'
        response_data['banner'] = 'None'
    except Exception as e:
        response_data['error'] = str(e)
    finally:
        sock.close()
    return response_data


def scan_ntp_port(host, port, timeout=1):
    message = '\x1b' + 47 * '\0'
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    response_data = {}

    # NTP 서버로 메시지 전송 및 응답 처리
    sock.sendto(message.encode('utf-8'), (host, port))
    response, _ = sock.recvfrom(1024)
    sock.close()

    unpacked = struct.unpack('!B B B b 11I', response)
    t = struct.unpack('!12I', response)[10] - 2208988800
    response_data = {
        'service':'NTP',
        'port': port,
        'state': 'open',
        'stratum': unpacked[1],
        'poll': unpacked[2],
        'precision': unpacked[3],
        'root_delay': unpacked[4] / 2**16,
        'root_dispersion': unpacked[5] / 2**16,
        'ref_id': unpacked[6],
        'server_time': time.ctime(t)
    }
    return response_data

def scan_smb_port(host, port, timeout=1):
    response_data = {}
    connection = Connection(uuid.uuid4(), host, 445)
    connection.connect(timeout=timeout)
    response_data = {
        'service': 'SMB',
        'port': 445,
        'state': 'open',
        'negotiated_dialect': connection.dialect
    }
    connection.disconnect()
    return response_data

import socket

def scan_vmware_port(host, port=902, timeout=1):
    response_data = {'service': 'VMWARE', 'port': port, 'state': 'closed'}

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))

        response = sock.recv(1024)
        sock.close()

        if response:
            response_data['state'] = 'open'
            try:
                response_data['banner'] = response.decode('utf-8').strip()
            except UnicodeDecodeError:
                response_data['banner'] = response.hex()
        else:
            response_data['state'] = 'no response'

    except socket.error as e:
        response_data['state'] = 'error'
        response_data['error_message'] = str(e)

    finally:
        if sock:
            sock.close()

    return response_data


def scan_mysql_port(host, port, timeout=1):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect((host, port))
    packet = s.recv(1024)
    s.close()

    if packet:
        end_index = packet.find(b'\x00', 5)
        server_version = packet[5:end_index].decode('utf-8')
        thread_id = struct.unpack('<I', packet[0:4])[0]
        cap_low_bytes = struct.unpack('<H', packet[end_index + 1:end_index + 3])[0]
        cap_high_bytes = struct.unpack('<H', packet[end_index + 19:end_index + 21])[0]
        server_capabilities = (cap_high_bytes << 16) + cap_low_bytes
        response_data = {
            'service': 'MY SQL',
            'port': port,
            'state': 'open',
            'server_version': server_version,
            'thread_id': thread_id,
            'server_capabilities': f'{server_capabilities:032b}'
        }
        return response_data
    

def scan_imap_port(host, port, timeout = 5):    
    response_data = {'service':'IMAP','port': port, 'state': 'closed'}
    
    try:
        if port == 993:
            imap_server = imaplib.IMAP4_SSL(host,port, timeout=timeout)
        else:
            imap_server = imaplib.IMAP4(host,port, timeout=timeout)
        # 배너정보 가져오기
        banner_info = imap_server.welcome
        response_data['state'] = 'open'
        response_data['banner'] = banner_info
        imap_server.logout()
        
    except imaplib.IMAP4.error as imap_error:
        response_data['state'] = 'error'
        response_data['error'] = imap_error
        
    except Exception as e:
        response_data['state'] = 'error'
        response_data['error'] = str(e)
        
    return response_data

#승희님 161    
def scan_snmp_port(host, port):
    community = 'public'
    response_data = {'service':'SNMP', 'port': port, 'state': 'closed'}

    # OID 객체 생성
    sysname_oid = ObjectIdentity('SNMPv2-MIB', 'sysName', 0) #시스템 이름
    sysdesc_oid = ObjectIdentity('SNMPv2-MIB', 'sysDescr', 0) #시스템 설명 정보 
    
    try: 
        #SNMPD 요청 생성 및 응답
        snmp_request = getCmd(
            SnmpEngine(),
            CommunityData(community),
            UdpTransportTarget((host, port), timeout=0.5, retries=1),
            ContextData(),
            ObjectType(sysname_oid),
            ObjectType(sysdesc_oid)
        )
        
        #요청에 대한 결과 추출
        error_indication, error_status, error_index, var_binds = next(snmp_request)
                
        if error_indication:
            response_data['state'] = 'error'
            response_data['error'] = str(error_indication)
        elif error_status:
            response_data['state'] = 'error'
            response_data['error'] = f'SNMP error state: {error_status.prettyPrint()} at {error_index}'
        else:
            response_data['state'] = 'open'
            for var_bind in var_binds:
                if sysname_oid.isPrefixOf(var_bind[0]):
                    response_data['sysname'] = var_bind[1].prettyPrint()
                elif sysdesc_oid.isPrefixOf(var_bind[0]):
                    response_data['sysinfo'] = var_bind[1].prettyPrint()
    
    except socket.timeout as timeout_error:
        response_data['state'] = 'error'
        response_data['error'] = timeout_error

    except socket.error as socket_error:
        response_data['state'] = 'error'
        response_data['error'] = socket_error

    except Exception as e:
        response_data['state'] = 'error'
        response_data['error'] = f'Unexpected error: {str(e)}'
    
    return response_data

# 영창님 21, 22 통합
def scan_ftp_ssh_port(host,port):
    if port == 21:
        service_name = 'FTP'
    elif port == 22:
        service_name = 'SSH'
    else:
        service_name = '알 수 없는 서비스'
        
    response_data = {'service':service_name,'port': port, 'state': 'closed'}

    try:
        # FTP 서버에 연결 시도
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)  # 연결 시도 시간 초과 설정
        result = sock.connect_ex((host, port))
        
        if result == 0:
            # 포트가 열려 있을 때
            banner = sock.recv(1024).decode('utf-8')
            response_data['state'] = 'open'
            response_data['banner'] = banner
        else:
            # 포트가 닫혀 있거나 필터링됐을 때
            response_data['state'] = 'closed'
        
    except socket.error as err:
        response_data['state'] = 'error'
        response_data['error'] = str(err)
        
    finally:
        # 소켓 닫기
        sock.close()
        
    return response_data

#다솜님 80
def scan_http_port(target_host, port):
    response_data = {
        'port': port,
        'state': 'closed',
    }

    try:
        with socket.create_connection((target_host, port), timeout=5) as sock:
            sock.sendall(b"HEAD / HTTP/1.1\r\nHost: " + target_host.encode() + b"\r\n\r\n")
            response = b""
            while b"\r\n\r\n" not in response:
                chunk = sock.recv(1024)
                if not chunk:
                    break
                response += chunk

            banner = response.decode("utf-8").strip()
            response_data['state'] = 'open'
            response_data['banner'] = banner
    except socket.timeout:
        response_data['state'] = 'timeout'
        response_data['error'] = 'Connection timed out'
    except socket.error as e:
        response_data['state'] = 'error'
        response_data['error'] = str(e)

    return response_data

#다솜님 110
def scan_pop3_port(target_host, port):
    response_data = {'service':'POP3','port': port, 'state': 'closed'}
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect((target_host, port))
        response = sock.recv(1024).decode('utf-8')
        response_data['state'] = 'open'
        response_data['banner'] = response.strip()
    except socket.timeout:
        response_data['state'] = 'no response'
    except Exception as e:
        response_data['state'] = 'error'
        response_data['error'] = str(e)
    finally:
        if sock:
            sock.close()

    return response_data

def scan_rdp_port(ip, port=3389):
    response_data = {'port': port, 'state': 'closed', 'error': None}
    if syn_scan(ip, port):
        try:
            # RDP 서버에 TCP 연결 시도
            connection = socket.create_connection((ip, port), timeout=10)
            response_data['state'] = 'open'
            # RDP 서비스의 배너 정보를 직접 받는 것은 일반적이지 않으므로, 연결 성공 여부만 확인
        except socket.error as err:
            response_data['state'] = 'open but unable to connect'
            response_data['error'] = str(err)
        finally:
            # 연결이 성공적으로 생성되었으면 종료
            if 'connection' in locals():
                connection.close()
    else:
        response_data['state'] = 'closed or filtered'
    return response_data

import socket

# 135
def scan_rsync_port(ip, port):
    response_data = {
        'port': port,
        'state': None,
        'banner': None,
        'error_message': None
    }
    try:
        socket.setdefaulttimeout(3)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((ip, port))
        response = s.recv(1024).decode('utf-8').strip()
        response_data['state'] = 'open'
        response_data['banner'] = response
    except socket.timeout:
        response_data['state'] = 'closed'
    except Exception as e:
        response_data['state'] = 'error'
        response_data['error_message'] = str(e)
    finally:
        s.close() if 's' in locals() else None

    return response_data