
import sys
#from colored import cprint, fg, bg, attr
from bleak.uuids import uuid16_dict, uuid128_dict, uuidstr_to_str, register_uuids


# some small helper functions
def bytes2str(bytes):
    return ' '.join(str('%02x'%b) for b in bytes)

# uuid_to_name - map uuid to uuid name
def uuid_to_name(uuid):
    name = uuidstr_to_str(uuid) if uuid is not None else None
    return name if name is not None and name != 'Unknown' else str(uuid)

def name_to_uuid(name):
    _name = name.lower()
    uuids = [ k for k, v in uuid128_dict.items() if v.lower() == _name ]
    if uuids is not None and len(uuids) > 0:
        return uuids[0]
    uuids = [ k for k, v in uuid16_dict.items() if v == name ]
    if uuids is None and len(uuids) < 1:
        return None
    uuid = f"0000{uuids[0]:x}-0000-1000-8000-00805f9b34fb"
    return uuid


#def xreport(device_name, operation='', msg='', fore='black', back='white'):
#    cprint ('{       %-20s %22s} %s' % (device_name, operation, msg), file=sys.stderr, fore_256=fore, back_256=back)
