#!/usr/python
#coding=utf-8
import json
import socket
import protocol
import hessian2
import threading
import thread
import Queue
import java
import json
import types
import datetime

__version__ = '0.1.0'

class Future(object) :
    FUTURES = {}
    def __init__(self, request, timeout = 1) :
        self.id = request.rid
        self.timeout = timeout
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.reqeust = request
        self.response = None
        Future.FUTURES[self.id] = self

    def get(self) :
        return self.getWithTimeout(self.timeout)
    
    def getWithTimeout(self, timeout) :
        if self.isDone() :
            return self.__doReturn()
        self.lock.acquire()
        try :
            self.cond.wait(self.timeout)
            if not self.isDone() :
                raise protocol.DubboTimeoutException('waiting response timeout. elapsed :' + str(self.timeout))
        finally :
            self.lock.release()

        return self.__doReturn()

    def setCallback(self, callback) :
        pass

    def isDone(self) :
        return self.response != None

    @classmethod
    def received(cls, response) :
        if response.rid in cls.FUTURES :
            future = Future.FUTURES[response.rid]
            del Future.FUTURES[response.rid]
            future.doReceived(response)

    def doReceived(self, response) :
        self.lock.acquire()
        try :
            self.response = response
            self.cond.notifyAll()
        finally :
            self.lock.release()

    def __doReturn(self) :
        if self.response.status != protocol.DubboResponse.OK :
            raise protocol.DubboException('DubboException : status = ' + \
                    str(self.response.status) + ' errorMsg = ' + \
                    str(self.response.errorMsg))
        elif self.response.exception != None :
            raise protocol.DubboException(self.response.exception)
        else :
            return self.response.result

class Endpoint(object) :
    def __init__(self, addr, readHandler) :
        self.addr = addr
        self.readHandler = readHandler
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.queue = Queue.Queue()

    def start(self) :
        self.sock.connect(self.addr)
        thread.start_new_thread(self.__sendLoop, ())
        thread.start_new_thread(self.__recvLoop, ())

    def send(self, data) :
        self.queue.put(data)

    def __sendLoop(self) :
        while True :
            data = self.queue.get()
            self.sock.sendall(data)

    def __recvLoop(self) :
        while True :
            header = self.sock.recv(protocol.HEADER_LENGTH)
            if header[:2] != protocol.MAGIC_NUMBER :
                return
            dataLength = protocol.getDataLength(header)
            data = ''
            if dataLength > 0 :
                data = self.sock.recv(dataLength)
            self.readHandler(header, data)

class DubboClient(object) :
    def __init__(self, addr) :
        self.addr = addr
        self.endpoint = Endpoint(addr, self.__recvResponse)
        self.endpoint.start()
    
    def invoke(self, request) :
        data = protocol.encodeRequest(request)
        timeout = request.data.attachments['timeout'] / 1000
        future = Future(request, timeout)
        self.endpoint.send(data)
        return future.get()

    def __recvResponse(self, header, data) :
        response = protocol.decode(header, data)
        if response.isEvent : 
            return
        Future.received(response)

class DubboProxy(object) :
    def __init__(self, client, classInfo, attachments) :
        self.client = client
        self.classInfo = classInfo
        self.attachments = attachments

    def invoke(self, name, args) :
        if not name in self.classInfo.methodMap :
            raise KeyError('interface ' + self.classInfo.thisClass + ' has no method name ' + str(name))
        methods = self.classInfo.methodMap[name]
        if len(methods) > 1 :
            method = self.__guessMethod(methods, args)
            if method == None :
                errorStr = 'can not find match method : ' + \
                        self.classInfo.thisClass + '.' + name + '(' + \
                        ', '.join([type(arg) for arg in args]) + \
                        ') maybe : '
                for method in methods :
                    errorStr += self.classInfo.thisClass + '.' + name + '(' + \
                            ', '.join(java.analyseParamTypes(self.__getParamType(method))) + \
                            ')'
                raise KeyError(errorStr)
        else :
            method = methods[0]
        
        paramType = self.__getParamType(method)

        request = protocol.DubboRequest()
        #print name, paramType, '(' + ', '.join([str(arg) for arg in args]) + ')', self.attachments
        data = protocol.RpcInvocation(name, paramType, args, self.attachments)
        request.data = data
        return self.client.invoke(request)

    def __guessMethod(self, methods, args) :
        for method in methods :
            paramTypes = java.analyseParamTypes(self.__getParamType(method))
            if len(paramTypes) != len(args) :
                continue
            ok = True
            for i in range(len(paramTypes)) :
                pType = type(args[i])
                jType = paramTypes[i]
                if \
                    (pType == types.BooleanType and jType == 'bool') \
                    or (pType == types.DictType and jType == 'dict') \
                    or (pType == types.FloatType and jType == 'float') \
                    or (pType == types.IntType and jType == 'int') \
                    or (pType == types.IntType and jType == 'long') \
                    or (pType == types.ListType and jType == 'list') \
                    or (pType == types.LongType and jType == 'long') \
                    or (pType == types.StringType and jType == 'string') \
                    or (pType == types.TupleType and jType == 'list') \
                    or (pType == types.UnicodeType and jType == 'string') \
                    or (pType == hessian2.Object and jType == args[i]._metaType) \
                    or (pType == hessian2.Binary and jType == 'byte') :
                    continue
                elif pType == types.NoneType :
                    continue
                else :
                    ok = False
                    break
            if ok :
                return method
        return None

                    

    def __getParamType(self, method) :
        paramType = self.classInfo.constantPool[method['descriptorIndex']][2]
        paramType = paramType[paramType.find('(') + 1 : paramType.find(')')]
        return paramType

    def __getattr__(self, name) :
        def dubbo_invoke(*args) :
            return self.invoke(name, args)
        return dubbo_invoke

class Dubbo(object):
    def __init__(self, addr, classPath = None, owner = None, customer = None, organization = None):
        self.client = DubboClient(addr)
        self.javaClassLoader = java.JavaClassLoader(classPath)
        if owner == None :
            owner = 'pythonGuest'
        if customer == None :
            customer = 'consumer-of-python-dubbo'
        self.attachments = {'owner' : owner, 'customer' : customer}

    def getProxy(self, interface, timeout = 1000, version = '1.0.0') :
        classInfo = self.javaClassLoader.findClass(interface)
        if classInfo == None :
            return None
        attachments = self.attachments.copy()
        attachments['path'] = interface
        attachments['interface'] = interface
        attachments['timeout'] = timeout
        attachments['version'] = version
        return DubboProxy(self.client, classInfo, attachments)

def __JsonDefault(obj): 
    if isinstance(obj, datetime.datetime) : 
        return obj.strftime('%Y-%m-%dT%H:%M:%S') 
    elif isinstance(obj, datetime.date) : 
        return obj.strftime('%Y-%m-%d') 
    elif isinstance(obj, hessian2.Object) :
        return obj.__dict__
    else: 
        raise TypeError('%r is not JSON serializable' % obj) 

def formatObject(obj) :
    return json.dumps(obj, ensure_ascii=False, indent=2, default = __JsonDefault)

if __name__ == '__main__' :
    client = Dubbo(('localhost', 20880), '../travel-service-interface-1.5.3.jar', owner = 'you.zhou', customer = 'consumer-of-travel-book')

    proxy = client.getProxy('com.qunar.travel.book.service.ITravelBookService2')

    print formatObject(proxy.getBookUserIds([719791, 719827, 719844]))

    antispamService = client.getProxy('com.qunar.travel.antispam.service.IAntispamService')

    print formatObject(antispamService.check([u'你好江泽民', u'64', u'呵呵']))

    #sortE = hessian2.Object('com.qunar.travel.query.param.SortDir', {'name' : 'DESC'})

    #print formatObject(proxy.getBookList('5763120@qunar', 0, 10, 1, sortE))

    #print proxy.getTravelBookDetail(692327L)

    #print proxy.clearCache(692327L)

    #proxy = client.getProxy('com.qunar.travel.destination.service.ITravelAlbumService', timeout = 3000)

    #print formatObject(proxy.findTravelAlbum(299914, 0, 10))
