import socket, threading, time, sys
from typing import Iterable
from .byteencoderdecoder import *
from .utils import *
from .dnstypes import *

# type Thread = threading.Thread


my_hostname: str = socket.gethostname()
my_ip: str = socket.gethostbyname(my_hostname)
ip_segments: list[str] = my_ip.split('.')
subnet_segments = ip_segments[:-1]
ips = ['.'.join(subnet_segments + [str(i)]) for i in range(2, 256)]
hostnames = {}

mdns_ip = '224.0.0.251'
mdns_ip6 = 'ff02::fb'
mdns_port = 5353
mdns_addr = (mdns_ip, mdns_port)

local_port = 30523
local_ip = '0.0.0.0'
local_addr = (local_ip, local_port)

lookup_port = 30524




def sequential_lookup_hostname_by_ip_batch(ip_batch: list[str]):
    for ip in ip_batch:
        print(f'processing ip: {ip}')
        try:
            hostname = socket.gethostbyaddr(ip)
            hostnames[ip] = hostname
        except Exception as e:
            hostnames[ip] = ''


def append_domain_to_qname(qname: str, domain: str):
    return '.'.join(qname.split('.') + [domain])

def append_local_to_qname(qname: str):
    return append_domain_to_qname(qname, 'local')

def create_multicast_socket(addr: tuple[str, int]=('0.0.0.0', 0), blocking: bool = False) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if sys.platform == 'win32':
        local_ip = get_local_ip()
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local_ip))
    sock.bind(addr)
    sock.setblocking(blocking)
    return sock



def get_subnet(include_trailing_dot: bool = True):
    ip = socket.gethostbyname(socket.gethostname())
    return '.'.join(ip.split('.')[:-1]) + ('.' * include_trailing_dot)

# threading.Thread(target=

# QTYPE_CODES: dict[int, str] = {val:key for key, val in QTYPES_DICT.items()}
# QTYPE_CODES: dict[int, str] = {1: 'A', 28: 'AAAA', 5: 'CNAME', 12: 'PTR', 33: 'SRV'}

class MDnsEncoder(ByteEncoder):
    def __init__(self, byteorder: Literal['big', 'little'] = 'big'):
        super().__init__(byteorder)

    def encode_length_prefixed_str(self, s: str, prefix_length: int = 0):
        if prefix_length == 0:
            prefix_length = get_min_bytelength(len(s))
        self.encode_int(len(s), 1)
        self.encode_str(s)

    def encode_dns_header(self, transaction_id:int=0, flags:int=0, qdcount:int=1, ancount:int=1, nscount:int=1, arcount:int=1):
        self.encode_int(0, 2) # Transaction ID = 0
        self.encode_int(0, 2) # Flags = Standard Query
        self.encode_int(qdcount, 2) # QDCOUNT = 1 question
        self.encode_int(0, 2) # ANCOUNT = 0 answers
        self.encode_int(0, 2) # NSCOUNT = 0 authority records
        self.encode_int(0, 2) # ARCOUNT = 0 additional records

    def encode_qname(self, qname: str):
        parts = qname.split('.')
        for part in parts:
            self.encode_length_prefixed_str(part, 1)
        self.encode_int(0, 1)

    def encode_qtype(self, qtype: str):
        qtype_int: int = QTYPES_DICT[qtype]
        # qtype has to be 16 bits, i.e. 2 bytes, so we encode with forced length=2 (bytes)
        self.encode_int(qtype_int, 2)

    def encode_qclass_and_unicast(self, qclass: int = 1, unicast_resp: bool = True):
        unicast_resp_int = int(unicast_resp)

        bs = str(unicast_resp_int)
        qclass_bs = '0'*14 + str(qclass)
        bs += qclass_bs
        self.encode_bitstr(bs)
    
    def encode_question(self, qname: str, qtype: str = 'A', qclass: int = 1, unicast_resp: bool = True) -> None:
        '''
        Encodes a SINGLE individual DNS question and appends the results to `self.bytes`
        This function does NOT on its own encode a full request, because it is missing the DNS header.
        It is designed that way to make it easier to use this class to encode both single and
        multiple question requests.
        '''
        self.encode_qname(qname)
        self.encode_qtype(qtype)
        self.encode_qclass_and_unicast(qclass, unicast_resp)


    def encode_request(self, qname: str|list[str], qtype: str = 'A', qclass: int = 1, unicast_resp: bool = True) -> bytes:
        '''
        Encodes a full mDNS request.  `qname` can be either a single qname or a list of qnames, and this determines
        how many individual questions are contained in the request.  All questions will be sent with the same single
        `qtype` though, so only use this function with multiple qnames if they all share the same qtype.
        '''
        qnames: list[str] = qname if isinstance(qname, list) else [qname]
        qdcount: int = len(qnames)
        self.encode_dns_header(qdcount=qdcount)
        for qname in qnames:
            self.encode_question(qname, qtype, qclass, unicast_resp)
        return self.bytes



def get_name_byte_meaning(x: int):
    top_two_bitmask = 0xc0 # bitmask: 11000000
    # AND x with top_two_bitmask, so the only bits that can be 1 are the top 2 bits, then
    # shift to the right by 6, moving those top two bits (whatever they are) to the 1s and 2s place
    # so if x = 11010101, then x&top_two_bitmask = 11000000, bitshifted 6 to the right is 00000011
    top_two_bits = (x & top_two_bitmask) >> 6
    # masked_x==0, meaning that the top 2 bits of x=='00', which corresponds to a normal name
    if top_two_bits == 0b00:
        return 'normal'
    # masked_x==3 (00000011), meaning that the top two bits of x=='11', which corresponds to a offset name
    elif top_two_bits == 0b11:
        return 'offset'
    raise ValueError(f'Error, byte: {x}, bitstr: {int_to_binstr(x)} does not start with 00 or 11, it is an invalid name meaning byte')



class MDnsDecoder(ByteDecoder):
    def __init__(self, b: bytes, byteorder: Literal['big', 'little'] = 'big', default_length_prefix_size: int = 1):
        super().__init__(b, byteorder, default_length_prefix_size)
        transaction_id, flags, questions, answers, authority_records, additional_records = self.decode_dns_header()
        self.transaction_id: int = transaction_id
        self.flags: int = flags
        self.questions_count: int = questions
        self.answers_count: int = answers
        self.authority_records_count: int = authority_records
        self.additional_records_count: int = additional_records

    # def get_name_by

    def decode_dns_header(self) -> tuple[int, int, int, int, int, int]:
        transaction_id: int = self.decode_int(2) # Transaction ID = 0
        flags: int = self.decode_int(2) # Flags = Standard Query
        question: int = self.decode_int(2) # QDCOUNT = 1 question
        answer: int = self.decode_int(2) # ANCOUNT = 0 answers
        authority_records: int = self.decode_int(2) # NSCOUNT = 0 authority records
        additional_records: int = self.decode_int(2) # ARCOUNT = 0 additional records
        return transaction_id, flags, question, answer, authority_records, additional_records

    def decode_rname(self) -> str:
        name_parts: list[str] = []
        while self.peek_next_bytes(1)[0] != 0:
            meaning = get_name_byte_meaning(self.bytes[self.pos])
            if meaning == 'normal':
                # It is a normal length prefix, handle it normally
                name_parts.append(self.decode_length_prefixed_str())
            else:
                # it is an offset.  Do complicated shit to find the offset, then manually decode the length prefixed
                # string located at that offset from the beginning of self.bytes
                b: bytes = self.get_next_bytes(2)
                # print(f'b: {b}')
                offset: int = ((b[0] & 0x3f) << 8) | b[1]
                # print(f'offset: {offset}')
                # length: int = int.from_bytes(self.bytes[offset:offset+1])
                dec = MDnsDecoder(self.bytes)
                dec.pos = offset
                name_parts.append(dec.decode_rname())
                return '.'.join(name_parts)


        # rrname ends with a null byte, so we just automatically consume that null byte here to make things simple
        self.get_next_bytes(1)
        return '.'.join(name_parts)

    def decode_two_bytes_15_1(self) -> tuple[bool, int]:
        '''
        Decodes the next two bytes as 1 bit as a bool, and the next 15 bits as an int
        '''
        two_bytes = self.get_next_bytes(2)
        num = int.from_bytes(two_bytes, self.byteorder)
        # I recognize that this is a very opaque line of code.  Basically cache_flush is a bool, but it is represented
        # literally by just 1 single bit.  The structure is like 1 bit for cache_flush, and then 15 bits for rrclass.
        # So it is two bytes, where rrclass is basically the whole two bytes, EXCEPT for the first bit which is cache_flush
        # So this line is creating a bitfield like 1000000000000000, and ANDing that with `num`
        # This makes it so that the only bit that can possibly be 1 is the left most bit (in the case that cache_flush is true),
        # otherwise all bits will be 0 (in the case cache_flush is false).  We then bitshift 15 to the right to move this bit
        # into the 1s place, and then cast to a bool.
        cache_flush: bool = bool((num & (1<<15)) >> 15)
        # Now we need to get the rrclass value from these two bytes.  We can just read the two bytes as a number, EXCEPT
        # for the annoying fact that the first bit could be a 1 (the cache_flush bit), which would ruin the result.
        # So we create a mask like 0111111111111111 (by bitshifting 1 to the left by 15 and then flipping the bits),
        # and AND it with num to set the leftmost bit of num to 0
        mask: int = flip_bits(1<<15)
        rrclass = num & mask
        return (cache_flush, rrclass)

    def decode_rdata(self, rdlength: int, rtype: int) -> dict:
        rdata: bytes = self.get_next_bytes(rdlength)
        if rtype == QTYPES_DICT['A']:
            if rdlength != 4:
                raise ValueError(f'Error, got rtype=1 (A), expected rdlength=4.  Got: rdlength={rdlength}')
            ip = '.'.join([str(part) for part in rdata])
            return {'ip': ip}
        elif rtype == QTYPES_DICT['AAAA']:
            if rdlength != 16:
                raise ValueError(f'Error, got rtype=28 (AAAA), expected rdlength=16.  Got: rdlength={rdlength}')
            ip = ':'.join([str(part) for part in rdata])
            return {'ip': ip}
        elif rtype == QTYPES_DICT['PTR']:
            dec = MDnsDecoder(self.bytes)
            dec.pos = self.pos - rdlength
            name = dec.decode_rname()
            return {'name': name}
        elif rtype == QTYPES_DICT['SRV']:
            priority: int = int.from_bytes(rdata[:2])
            # priority: int = self.decode_int(2)
            # weight: int = self.decode_int(2)
            weight: int = int.from_bytes(rdata[2:4])
            # port: int = self.decode_int(2)
            port: int = int.from_bytes(rdata[4:6])
            dec = MDnsDecoder(self.bytes)
            dec.pos = self.pos - rdlength + 6
            target: str = dec.decode_rname()
            # target: str = rdata[6:].decode()
            # target: str = self.decode_rrname()
            return {'priority': priority, 'weight': weight, 'port': port, 'target': target}
        elif rtype == QTYPES_DICT['TXT']:
            bytes_consumed: int = 0
            dct = {}
            dec = MDnsDecoder(self.bytes)
            start_pos = self.pos - rdlength
            dec.pos = start_pos
            unnamed_val_count = 0
            while bytes_consumed < rdlength:
                s = dec.decode_length_prefixed_str()
                if '=' in s:
                    key, val = s.split('=')
                    dct[key] = val
                else:
                    key = f'unnamed_val{unnamed_val_count}'
                    dct[key] = s
                    # raise RuntimeError(f'Error, "=" not found in TXT value: {s}')
                bytes_consumed = dec.pos - start_pos
            return dct
            # return {'rdata': rdata}
        raise ValueError(f'Sorry, rtypes other than 1 (\'A\') have not been implemented yet, got: {rtype} ({QTYPE_CODES[rtype]})')

    def decode_resource_record(self):
        rrname: str = self.decode_rname()
        # print(f'rrname: {rrname}')
        rrtype_int: int = self.decode_int(2)
        if not rrtype_int in QTYPE_CODES:
            print(f'Ran into error.  pos: {self.pos}')
        rrtype = QTYPE_CODES[rrtype_int]
        # print(f'rrtype: {rrtype}')
        cache_flush, rrclass_int = self.decode_two_bytes_15_1()
        rrclass: str = QCLASS_CODES[rrclass_int]
        # print(f'cache_flush: {cache_flush}')
        ttl: int = self.decode_int(4)
        # print(f'ttl: {ttl}')
        rdlength: int = self.decode_int(2)
        # print(f'rdlength: {rdlength}')
        rdata = self.decode_rdata(rdlength, rrtype_int)
        # dct = {'name': rrname, 'rrtype': rrtype, 'cache_flush': cache_flush, 
        #        'rrclass': rrclass, 'ttl': ttl, 'rdlength': rdlength, 'rdata': rdata}

        return ResourceRecord(rrname, rrtype, cache_flush, rrclass, ttl, rdata)

    def decode_question(self) -> DNSQuestion:
        qname: str = self.decode_rname()
        qtype_int: int = self.decode_int(2)
        qtype = QTYPE_CODES[qtype_int]
        unicast_resp, qclass = self.decode_two_bytes_15_1()
        return DNSQuestion(qname, qtype, qclass, unicast_resp)
        # return {'qname': qname, 'qtype': qtype, 'qclass': qclass, 'unicast_response': unicast_resp}


    def decode_response(self) -> DNSResponse:#tuple[list[dict], list[ResourceRecord], list[ResourceRecord]]:
        dct: dict = {}
        # dns_header_bytes: bytes = self.decode_dns_header()
        # transaction_id, flags, num_questions, num_answers, num_authority_records, num_additional_records = self.decode_dns_header()
        # print(f'questions: {self.questions_count}')
        # print(f'answers: {self.answers_count}')
        questions = []
        answers = []
        additional_records = []

        for i in range(self.questions_count):
            questions.append(self.decode_question())

        # print(f'pos after decoding questions: {self.pos}')
        # print(f'bytes remaining after decoding questions')
        # print(self.bytes[self.pos:])
        # print('\n\n\n\n')

        for i in range(self.answers_count):
            answers.append(self.decode_resource_record())


        # print(f'pos after decoding answers: {self.pos}')
        # print(f'bytes remaining after decoding answers')
        # print(self.bytes[self.pos:])
        # print('\n\n\n\n')

        for _ in range(self.authority_records_count):
            additional_records.append(self.decode_resource_record())

        for _ in range(self.additional_records_count):
            additional_records.append(self.decode_resource_record())

        return DNSResponse(questions, answers, additional_records, self.bytes)
        # return questions, answers, additional_records



requests_sent: int = 0
responses: list [DNSResponse] = []



def get_services(qname: str):
    '''
    Returns a list of all service names advertised for the given qname (e.g. _ipp._tcp.local)
    '''
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    enc = MDnsEncoder()
    enc.encode_request(qname, 'PTR')
    sock.sendto(enc.bytes, mdns_addr)
    resp_bytes, ret_addr =  sock.recvfrom(4096)
    # sock.sendto(
    pass




# def receieve_dns_resp(sock: socket.socket):
#     resp_bytes, resp_addr = sock.recvfrom(4096)
#     dns_resp = DNSResponse(
#
#
#     pass







enc = MDnsEncoder()

q = []
a = []
r = []
dns_responses: list[DNSResponse] = []
dns_resp: DNSResponse
req_bytes: bytes

def get_rdns_ip_name(ip: str):
    return f'{reverse_ip_segments(ip)}.in-addr.arpa'

def get_local_ip():
    return socket.gethostbyname(socket.gethostname())

def send_dns_req(qname: str, qtype: str, qclass: int = 1, unicast_resp: bool = True, blocking_socket: bool = False) -> socket.socket:
    global req_bytes, local_port
    enc: MDnsEncoder = MDnsEncoder()
    req_bytes = enc.encode_request(qname, qtype, qclass, unicast_resp)
    sock = create_multicast_socket(('0.0.0.0', local_port))
    local_port += 1
    # sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # # if this is running on windows
    # if sys.platform == 'win32':
    #     local_ip = get_local_ip()
    #     socket.gethostbyname(socket.gethostname())
    #     sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local_ip))
    # sock.bind(local_addr)
    # sock.setblocking(blocking_socket)
    sock.sendto(req_bytes, mdns_addr)
    return sock


def send_rdns_req(ip: str, blocking_socket: bool = False, unicast_resp: bool = True):#-> socket.socket:
    global req_bytes, lookup_port
    qtype: str = 'PTR'
    qclass: int = 1
    enc: MDnsEncoder = MDnsEncoder()
    qname = get_rdns_ip_name(ip)
    print(f'qname: {qname}\nqtype: {qtype}\nqclass: {qclass}')
    req_bytes = enc.encode_request(qname, qtype, qclass, unicast_resp)
    print(req_bytes)
    # exit()
    sock = create_multicast_socket(('0.0.0.0', 0), blocking_socket)
    lookup_port += 1
    sock.sendto(req_bytes, mdns_addr)
    return sock


def listen_for_dns_responses(sock: socket.socket, seconds: float = 2.0, max_responses: int = -1):
    global dns_responses
    start_time: float = time.time()
    curr_time: float = time.time()
    time_elapsed = curr_time - start_time
    local_responses: list[DNSResponse] = []

    # Only run while less than `seconds` time has elapsed
    while time_elapsed < seconds:
        # read and decode all messages in the socket queue
        receieved_response: bool = True
        while receieved_response:
            try:
                resp_bytes, resp_addr = sock.recvfrom(8192)
                # print(f'resp_bytes: {resp_bytes}')
            except BlockingIOError as e:
                receieved_response = False
                break
            if resp_bytes:
                dec = MDnsDecoder(resp_bytes)
                dns_resp = dec.decode_response()
                dns_resp.ip = resp_addr[0]
                # print(f'received response from addr: {resp_addr}: {dns_resp}')
                dns_responses.append(dns_resp)
                local_responses.append(dns_resp)
                if max_responses > 0:
                    # if max_responses <= 0, don't do anything because that represents "get all responses"
                    # So in this case max_responses is some positive value, and we return early once local_responses reaches that length
                    if len(local_responses) >= max_responses:
                        sock.close()
                        return local_responses
            else:
                receieved_response = False
            # except Exception as _:
            #     receieved_response = False
            # time.sleep(0.01)

        time.sleep(0.1)
        curr_time = time.time()
        time_elapsed = curr_time - start_time
    sock.close()
    return local_responses



def receieve_and_decode_resp(sock: socket.socket):
    global q, a, r, dns_resp
    resp_bytes, resp_addr = sock.recvfrom(4096)
    print(f'Received response from addr: {resp_addr}')
    dec = MDnsDecoder(resp_bytes)
    dns_resp = dec.decode_response()
    q, a, r = dns_resp.record_lists()
    # q, a, r = dec.decode_response()
    print(f'questions: {q}')
    print(f'answers: {a}')
    print(f'additional records: {r}')


def resolve_hostname(hostname: str) -> str:
    sock: socket.socket = send_dns_req(hostname, 'A')
    local_responses: list[DNSResponse] = listen_for_dns_responses(sock, 1.5, 1)
    if len(local_responses) > 0:
        resp: DNSResponse = local_responses[0]
        if len(resp.answers) > 0:
            return resp.answers[0].rdata['ip']
    raise RuntimeError(f'Error, failed to resolve hostname: {hostname}')




