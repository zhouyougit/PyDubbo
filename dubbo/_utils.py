import json
import datetime
import _model

def __JsonDefault(obj): 
    if isinstance(obj, datetime.datetime) : 
        return obj.strftime('%Y-%m-%dT%H:%M:%S') 
    elif isinstance(obj, datetime.date) : 
        return obj.strftime('%Y-%m-%d') 
    elif isinstance(obj, _model.Object) :
        return obj.__dict__
    else: 
        raise TypeError('%r is not JSON serializable' % obj) 

def formatObject(obj) :
    return json.dumps(obj, ensure_ascii=False, indent=2, default = __JsonDefault)

def printByteStr(encodeStr) :
    outstr = ''
    col = 0
    for c in encodeStr :
        outstr += '%02x ' % (ord(c))
        col += 1
        if col >= 16 :
            col = 0
            outstr += '\n'
    print outstr


