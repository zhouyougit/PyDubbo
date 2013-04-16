
import threading
import struct
import hessian2

HEADER_LENGTH = 16
MAGIC_NUMBER = '\xda\xbb'
FLAG_REQUEST = 0x80
FLAG_TWOWAY = 0x40
FLAG_EVENT = 0x20
HESSIAN2_CONTENT_TYPE_ID = 2

DOUBLE_VERSION = '2.3.3'

RESPONSE_NULL_VALUE = 2
RESPONSE_VALUE = 1
RESPONSE_WITH_EXCEPTION = 0

class RpcInvocation(object) :
    def __init__(self, methodName = None, paramTypes = None, params = None, attachments = None) :
        self.methodName = methodName
        self.paramTypes = paramTypes or ''
        self.params = params or []
        self.attachments = attachments or {}

class DubboRequest(object) :
    ridLock = threading.Lock()
    nextRid = 0
    def __init__(self, twoWay = True, event = False, broken = False, data = None) :
        if self.ridLock.acquire() :
            self.rid = DubboRequest.nextRid
            DubboRequest.nextRid += 1
            self.ridLock.release()

        self.isTwoWay = twoWay
        self.isEvent = event
        self.isBroken = broken
        self.data = data

    def __str__(self) :
        return 'DubboRequest :' + str(self.__dict__)

class DubboResponse(object) :
    OK = 20
    CLIENT_TIMEOUT = 30
    SERVER_TIMEOUT = 31
    BAD_REQUEST = 40
    BAD_RESPONSE = 50
    SERVICE_NOT_FOUND = 60
    SERVICE_ERROR = 70
    SERVER_ERROR = 80
    CLIENT_ERROR = 90
    def __init__(self, rid) :
        self.rid = rid
        self.status = DubboResponse.OK
        self.isEvent = False
        self.version = ''
        self.errorMsg = ''
        self.result = None
        self.exception = None

    def isHeartBeat(self) :
        return self.event and self.result == None

    def setEvent(self, reult) :
        self.event = True
        self.result = result

    def __str__(self) :
        return 'DubboResponse :' + str(self.__dict__)

class DubboException(Exception) :
    def __init__(self, data) :
        self.data = data
    def __str__(self) :
        return 'DubboException :' + str(self.data)

class DubboTimeoutException(Exception) :
    def __init__(self, data) :
        self.data = data
    def __str__(self) :
        return 'DubboTimeoutException :', self.data

def encodeRequestData(invocation) :
    out = hessian2.Hessian2Output()
    out.writeObject(DOUBLE_VERSION)
    out.writeObject(invocation.attachments['path'])
    out.writeObject(invocation.attachments['version'])
    out.writeObject(invocation.methodName)
    out.writeObject(invocation.paramTypes)
    for param in invocation.params :
        #oo = hessian2.Hessian2Output()
        #oo.writeObject(param)
        #hessian2.printByteStr(oo.getByteString())
        out.writeObject(param)
    out.writeObject(invocation.attachments)
    return out.getByteString()

def encodeRequest(request) :
    if not isinstance(request, DubboRequest) :
        raise TypeError('encodeRequest only support DubboRequest type')
    header = ''
    header += MAGIC_NUMBER
    flag = HESSIAN2_CONTENT_TYPE_ID | FLAG_REQUEST
    if request.isEvent :
        flag |= FLAG_EVENT
    if request.isTwoWay :
        flag |= FLAG_TWOWAY

    header += chr(flag)
    header += '\x00'
    header += struct.pack('>q', request.rid)

    data = None
    if request.isEvent :
        pass
        #data = encodeEventData(request.getData())
    else :
        data = encodeRequestData(request.data)

    dataLength = len(data)
    header += struct.pack('>i', dataLength)

    return header + data

def getDataLength(header) :
    return struct.unpack('>i', header[12:])[0]

def getRequestId(header) :
    return struct.unpack('>q', header[4:12])[0]

def decodeResponseData(response, input) :
    flag = input.readObject()
    if flag == RESPONSE_NULL_VALUE :
        response.result = None
    elif flag == RESPONSE_VALUE :
        response.result = input.readObject()
    elif flag == RESPONSE_WITH_EXCEPTION :
        response.exception = input.readObject()

def decode(header, data) :
    flag = ord(header[2])
    status = ord(header[3])
    rid = getRequestId(header)
    if flag & FLAG_REQUEST != 0 :
        #request
        return None
    else :
        response = DubboResponse(rid)
        response.status = status
        response.isEvent = flag & FLAG_EVENT
        input = hessian2.Hessian2Input(data)
        if response.status != DubboResponse.OK :
            response.errorMsg = input.readObject()
        else :
            if response.isEvent :
                response.result = input.readObject()
            else :
                decodeResponseData(response, input)
        return response

if __name__ == '__main__' :
    request = DubboRequest()
    data = encodeRequest(request)
    hessian2.printByteStr(data)
