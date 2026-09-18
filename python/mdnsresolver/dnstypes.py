from dataclasses import dataclass
from typing import Literal, Any
from .utils import *


service_types_path: str = os.path.join(netex_root, 'service_types.csv')
with open(service_types_path, 'r') as f:
    partial_service_idents = [ident.strip() for ident in f.read().split(',')]

full_service_idents = [f'{ident}.local' for ident in partial_service_idents]


QTYPES_DICT: dict[str, int] = {'A': 1, 'AAAA': 28, 'CNAME': 5, 'PTR': 12, 'SRV': 33, 'TXT': 16}
QTYPE_CODES: dict[int, str] = invert_dict(QTYPES_DICT)

QCLASS_DICT: dict[str, int] = {'IN': 1, 'ANY': 255}
QCLASS_CODES: dict[int, str] = {1: 'IN', 255: 'ANY'}


@dataclass
class DNSQuestion:
    qname: str
    qtype: str|int
    qclass: str|int
    unicast_response: bool

    def __post_init__(self):
        if isinstance(self.qtype, int):
            if not self.qtype in QTYPE_CODES:
                raise ValueError(f'Error, qtype int value: {self.qtype} not known')
            self.qtype = QTYPE_CODES[self.qtype]

        if isinstance(self.qclass, int):
            if not self.qclass in QCLASS_CODES:
                raise ValueError(f'Error, qclass int value: {self.qclass} not known')
            self.qclass = QCLASS_CODES[self.qclass]

    def as_dict(self):
        return {'qname': self.qname, 'qtype': self.qtype, 'qclass': self.qclass}


@dataclass
class DNSHeader:
    transaction_id: int
    flags: int
    question: int
    answer: int
    authority_records: int
    additional_records: int


@dataclass
class ResourceRecord:
    rname: str
    rtype: str
    cache_flush: bool
    rclass: str
    ttl: int
    rdata: dict[str, Any]

    def as_dict(self):
        return {'rname': self.rname, 'rtype': self.rtype, 'rclass': self.rclass, 'rdata': self.rdata}

    def __lt__(self, other):
        if isinstance(other, ResourceRecord):
            return self.rname < other.rname
        elif isinstance(other, str):
            return self.rname < other
        else:
            raise TypeError(f'Error, ResourceRecord can only be compared to ResourceRecord|str.  Got: {type(other)}')

    def __gt__(self, other):
        if isinstance(other, ResourceRecord):
            return self.rname > other.rname
        elif isinstance(other, str):
            return self.rname > other
        else:
            raise TypeError(f'Error, ResourceRecord can only be compared to ResourceRecord|str.  Got: {type(other)}')

    def __eq__(self, other):
        if not isinstance(other, ResourceRecord):
            raise TypeError(f'Error, ResourceRecord can only be checked for equality against ResourceRecord.  Got: {type(other)}')
        return (self.rname == other.rname) and (self.rtype == other.rtype) and (self.rclass == other.rclass) and (self.rdata==other.rdata)

    def __str__(self):
        s: str = f'Response for: {self.rname}\n'
        # Ensure that name and target keys show up first (since they are the main thing), not buried at the end/middle of the rdata items
        priority_keys = ['name', 'target']
        for key in priority_keys:
            if key in self.rdata:
                val = self.rdata[key]
                keyname: str = key.capitalize()
                s += f'\t{keyname}: {val}\n'

        for key, val in self.rdata.items():
            if key not in priority_keys:
                keyname: str = key.capitalize() if key.lower() != 'ip' else 'IP'
                s += f'\t{keyname}: {val}\n'

        s += '\nRecord info\n'
        s += f'\tTTL: {self.ttl}\n'
        s += f'\tType: {self.rtype}\n'
        s += f'\tClass: {self.rclass}\n'
        s += f'\tCache flush: {self.cache_flush}'
        return s


@dataclass
class ServiceRecord:
    name: str
    priority: int
    weight: int
    port: int
    target: str
    ip: str

    @staticmethod
    def from_resource_record(resource_record: ResourceRecord, ip: str = ''):
        rdata: dict = resource_record.rdata
        return ServiceRecord(resource_record.rname, rdata['priority'], rdata['weight'], rdata['port'], rdata['target'], ip)

    def as_dict(self):
        return {'name': self.name, 'target': self.target, 'port': self.port, 'weight': self.weight, 'priority': self.priority, 'ip': self.ip}

    def __hash__(self):
        return hash(f'{self.name}_{self.target}_{self.weight}_{self.port}_{self.priority}')





type TextRecord = dict[str, str]


@dataclass
class DNSResponse:
    questions: list[DNSQuestion]
    answers: list[ResourceRecord]
    additional_records: list[ResourceRecord]
    bytes: bytes
    ip: str = ''

    def all_records(self) -> list[ResourceRecord]:
        return self.answers + self.additional_records

    def record_lists(self) -> tuple[list[DNSQuestion], list[ResourceRecord], list[ResourceRecord]]:
        return self.questions, self.answers, self.additional_records

    def records_with_rtype(self, rtype: str) -> list[ResourceRecord]:
        lst: list[ResourceRecord] = []
        for record in self.answers:
            if record.rtype == rtype:
                lst.append(record)
        for record in self.additional_records:
            if record.rtype == rtype:
                lst.append(record)
        return lst

    def get_ip(self, ip_type: Literal['ipv4', 'ipv6'] = 'ipv4') -> str:
        if self.ip:
            return self.ip
        if ip_type == 'ipv4':
            rtype: str = 'A'
        elif ip_type == 'ipv6':
            rtype: str = 'AAAA'
        else:
            raise ValueError(f'Error, ip_type must be ipv4 or ipv6, got: {ip_type}')

        for rec in self.all_records():
            if rec.rtype == rtype:
                if 'ip' in rec.rdata:
                    return rec.rdata['ip']
        return ''

    def as_dict(self):
        qd: list[dict] = [question.as_dict() for question in self.questions]
        ad: list[dict] = [answer.as_dict() for answer in self.answers]
        rd: list[dict] = [rec.as_dict() for rec in self.additional_records]
        return {'questions': qd, 'answers': ad, 'additional_records': rd}

    
    def get_service_names(self) -> list[str]:
        service_names: list[str] = []
        for answer in self.answers:
            # only process answers with rtype PTR
            if answer.rtype != 'PTR':
                continue
            if answer.rname in full_service_idents:
                if 'name' in answer.rdata:
                    service_names.append(answer.rdata['name'])
                else:
                    raise RuntimeError(f"Error, 'name' not found in answer.rdata for answer: {answer}")

        for record in self.additional_records:
            # only process records with rtype SRV
            if record.rtype != 'SRV':
                continue
            for ident in full_service_idents:
                if record.rname in ident:
                    if not (record.rname in service_names):
                        service_names.append(record.rname)
                    break
        return service_names


    def get_all_service_records(self) -> list[ServiceRecord]:
        service_records: list[ServiceRecord] = []
        ip = self.get_ip()
        for record in self.additional_records:
            if record.rtype == 'SRV':
                service_records.append(ServiceRecord.from_resource_record(record, ip))

        return service_records


    def get_noncovered_services(self) -> list[str]:
        '''
        Returns all services contained in `self.answers` which are 
        not represented with service responses in `self.additional_records`

        e.g. if `answers` contains _ipp._tcp.local, _http._tcp.local, and _https._tcp.local,
        and `additional_records` only contains responses for '_http._tcp.local`, and `_https._tcp.local`,
        then this function will return _ipp._tcp.local.  Since that is the service contained in answers,
        but with no corresponding resource record in `additional_records.`
        '''
        service_names = [rec.qname for rec in self.questions]
        noncovered_services: list[str] = []
        for service_name in service_names:
            found_service: bool = False
            for rec in self.additional_records:
                if rec.rname.endswith(service_name):
                    found_service = True
                    break
            if not found_service:
                noncovered_services.append(service_name)
        return noncovered_services

    def __hash__(self):
        return hash(self.bytes)

    def __eq__(self, other):
        if isinstance(other, DNSResponse):
            pass
        return False




def print_resource_record(record: ResourceRecord, indented: bool = False, visual_separator: bool = False) -> None:
    s: str = str(record) if not indented else '\t' + str(record).replace('\n', '\n\t')
    if visual_separator:
        lines_lengths: list[int] = [len(line.replace('\t', '    ')) for line in s.split('\n')]
        longest_length: int = max(lines_lengths)
        border_line: str = '-' * int(longest_length * 1.2)
        s = f'{s}\n{border_line}\n'
    print(s)


class NetworkDevice:
    def __init__(self, ip: str, services: list[str]):
        self.ip: str = ip
        self.services: list[str] = services
        # self.service_idents: list[str] = 



