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
import time
from constants import *
import _model
from _utils import formatObject

__version__ = '0.1.0'

RpcContext = threading.local()

class Future(object) :
    FUTURES = {}
    FUTURES_LOCK = threading.Lock()
    def __init__(self, request, timeout) :
        self.id = request.rid
        self.timeout = timeout
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.reqeust = request
        self.response = None
        self.timestamp = time.time()
        Future.FUTURES_LOCK.acquire()
        try :
            Future.FUTURES[self.id] = self
        finally :
            Future.FUTURES_LOCK.release()

    def get(self) :
        return self.getWithTimeout(self.timeout)
    
    def getWithTimeout(self, timeout) :
        if self.isDone() :
            return self.__doReturn()
        with self.lock :
            if not self.isDone() :
                self.cond.wait(self.timeout)
                if not self.isDone() :
                    raise protocol.DubboTimeoutException('waiting response timeout. elapsed :' + str(self.timeout))

        return self.__doReturn()

    def setCallback(self, callback) :
        pass

    def isDone(self) :
        return self.response != None

    @classmethod
    def received(cls, response) :
        if response.rid in cls.FUTURES :
            Future.FUTURES_LOCK.acquire()
            try :
                if response.rid in cls.FUTURES :
                    future = Future.FUTURES[response.rid]
                    del Future.FUTURES[response.rid]
                else :
                    return
            finally :
                Future.FUTURES_LOCK.release()
            future.doReceived(response)

    def doReceived(self, response) :
        with self.lock :
            self.response = response
            self.cond.notifyAll()

    def __doReturn(self) :
        if self.response.status != protocol.DubboResponse.OK :
            raise protocol.DubboException('DubboException : status = ' + \
                    str(self.response.status) + ' errorMsg = ' + \
                    str(self.response.errorMsg))
        elif self.response.exception != None :
            raise protocol.DubboException(self.response.exception)
        else :
            return self.response.result

    @classmethod
    def _checkTimeoutLoop(cls) :
        while True :
            try :
                for future in Future.FUTURES.values() :
                    if future.isDone() :
                        continue
                    if (time.time() - future.timestamp) > future.timeout :
                        print 'find timeout future'
                        response = protocol.DubboResponse(future.id)
                        response.status = protocol.DubboResponse.SERVER_TIMEOUT
                        response.seterrorMsg = 'waiting response timeout. elapsed :' + str(future.timeout)
                        Future.received(response)
                time.sleep(0.03)
            except Exception, e:
                print 'check timeout loop' + str(e)

thread.start_new_thread(Future._checkTimeoutLoop, ())

class Endpoint(object) :
    def __init__(self, addr, readHandler) :
        self.addr = addr
        self.readHandler = readHandler
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.queue = Queue.Queue()
        self.lock = threading.Lock()
        self.cTime = None

    def start(self) :
        self.sock.connect(self.addr)
        self.cTime = time.time()
        thread.start_new_thread(self.__sendLoop, ())
        thread.start_new_thread(self.__recvLoop, ())

    def send(self, data) :
        self.queue.put(data)

    def __sendLoop(self) :
        while True :
            try :
                data = self.queue.get()
                self.sock.sendall(data)
            except Exception, e :
                print 'send error'
                self.__reconnection()

    def __reconnection(self) :
        if not self.lock.acquire(False) :
            self.lock.acquire()
            self.lock.release()
            return
        try :
            print 'start reconnection'
            while True :
                try :
                    print 'start shutdown'
                    try :
                        self.sock.shutdown(socket.SHUT_RDWR)
                    except :
                        pass
                    print 'finish shutdown'
                    del self.sock
                    print 'create new socket'
                    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    print 'create new socket finish'
                    self.cTime = time.time()
                    print 'start connect'
                    self.sock.connect(self.addr)
                    print 'finish connect'
                    break
                except socket.error :
                    if time.time() - self.cTime < 2 :
                        time.sleep(2)
        finally :
            self.lock.release()
        print 'end reconnection'

    def __recv(self, length) :
        while True :
            data = self.sock.recv(length)
            if not data :
                print 'recv error'
                self.__reconnection()
                continue
            return data

    def __recvLoop(self) :
        while True :
            try :
                header = self.__recv(protocol.HEADER_LENGTH)
                if header[:2] != protocol.MAGIC_NUMBER :
                    continue
                while len(header) < protocol.HEADER_LENGTH :
                    temp = self.__recv(protocol.HEADER_LENGTH - len(header))
                    header += temp
                dataLength = protocol.getDataLength(header)
                data = ''
                while len(data) < dataLength :
                    temp = self.__recv(dataLength - len(data))
                    data += temp
                self.readHandler(header, data)
            except Exception, e :
                print 'recv loop' + str(e)

def _getRequestParam(request, key, default = None) :
    if key in request.data.attachments :
        return request.data.attachments[key]
    return default

class DubboClient(object) :
    def __init__(self, addr) :
        self.addr = addr
        self.endpoint = Endpoint(addr, self.__recvResponse)
        self.endpoint.start()
    
    def invoke(self, request) :
        data = protocol.encodeRequest(request)
        timeout = _getRequestParam(request, KEY_TIMEOUT)
        withReturn = _getRequestParam(request, KEY_WITH_RETURN, True)
        async = _getRequestParam(request, KEY_ASYNC, False)
        if not withReturn :
            self.endpoint.send(data)
            return

        if async :
            future = Future(request, timeout)
            RpcContext.future = future
            self.endpoint.send(data)
            return
        else :
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
        if KEY_METHOD in attachments :
            self.methodConfig = attachments[KEY_METHOD]
            del attachments[KEY_METHOD]
        else :
            self.methodConfig = {}

    def _updateConfig(self, config) :
        config = config.copy()
        if KEY_METHOD in config :
            methodConfig = config[KEY_METHOD]
            del config[KEY_METHOD]
        else :
            methodConfig = None
        self.attachments.update(config)
        if methodConfig :
            for methodName, methodConfig in methodConfig.items() :
                if methodName not in self.methodConfig :
                    self.methodConfig[methodName] = methodConfig.copy()
                else :
                    self.methodConfig[methodName].update(methodConfig)

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
        attachments = self.attachments.copy()
        if name in self.methodConfig :
            attachments.update(self.methodConfig[name])
        print attachments
        #print name, paramType, '(' + ', '.join([str(arg) for arg in args]) + ')', self.attachments
        data = protocol.RpcInvocation(name, paramType, args, attachments)
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
                    or (pType == _model.Object and jType == args[i]._metaType) \
                    or (pType == _model.Binary and jType == 'byte') :
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

def _getAndDelConfigParam(config, key, default = None) :
    if config and key in config :
        value = config[key]
        del config[key]
        return value
    else :
        return default

class Dubbo(object):
    def __init__(self, addr, config = None):
        if config :
            config = config.copy()
        else :
            config = {}
        self.config = config

        self.client = DubboClient(addr)
        
        classpath = _getAndDelConfigParam(config, KEY_CLASSPATH)
        self.javaClassLoader = java.JavaClassLoader(classpath)

        owner = _getAndDelConfigParam(config, KEY_DUBBO_OWNER, DEFAULT_DUBBO_OWNER)
        customer = _getAndDelConfigParam(config, KEY_DUBBO_CUSTOMER, DEFAULT_DUBBO_CUSTOMER)
        self.attachments = {KEY_OWNER : owner, KEY_CUSTOMER : customer}
        
        for key, value in self.config.items() :
            if key == KEY_REFERENCE :
                continue
            self.attachments[key] = value

        if KEY_REFERENCE not in self.config :
            self.config[KEY_REFERENCE] = {}

    def getProxy(self, interface, **args) :
        classInfo = self.javaClassLoader.findClass(interface)
        if classInfo == None :
            return None
        attachments = self.attachments.copy()
        attachments[KEY_PATH] = interface
        attachments[KEY_INTERFACE] = interface

        if interface in self.config[KEY_REFERENCE] :
            attachments.update(self.config[KEY_REFERENCE][interface])

        if args :
            for key, value in args.items() :
                attachments[key] = value

        self.__checkAttachments(attachments)

        return DubboProxy(self.client, classInfo, attachments)

    def __checkAttachments(self, attachments) :
        if KEY_TIMEOUT not in attachments :
            attachments[KEY_TIMEOUT] = DEFAULT_TIMEOUT
        if KEY_VERSION not in attachments :
            attachments[KEY_VERSION] = DEFAULT_SERVICE_VERSION

outQueue = Queue.Queue()

def th(proxy, index) :
    while True :
        try :
            proxy.getBookUserIds([719791, 719827, 719844])
            result = RpcContext.future.get()
            outQueue.put(str(index) + ' ' + str(len(formatObject(result))))
            time.sleep(1)
        except :
            print 'call error'

def pth() :
    while True :
        msg = outQueue.get()
        print msg

if __name__ == '__main__' :
    config = { \
            'owner' : 'pythonUser', \
            'customer' : 'consumer-of-python', \
            'classpath' : '../travel-service-interface-1.5.3.jar', \
            'reference' : { \
                'com.qunar.travel.book.service.ITravelBookService2' : { \
                    'method' : { \
                        'getBookUserIds' : {
                            'async' : True
                        },
                    }
                }
            }
        }
    client = Dubbo(('localhost', 20880), config)

    proxy = client.getProxy('com.qunar.travel.book.service.ITravelBookService2', timeout = 0.5)
    start = time.time()
    result = proxy.getBookUserIds([719791, 719827, 719844])
    print result
    print formatObject(RpcContext.future.get())

    print formatObject(proxy.getTravelBookOverView(719791))
    '''
    thread.start_new_thread(pth, ())

    for i in range(10) :
        thread.start_new_thread(th, (proxy, i))
    time.sleep(100000)
    
    result = []
    for i in range(100) :
        proxy.getBookUserIds([719791, 719827, 719844])
        result.append(RpcContext.future)

    for result in result :
        print formatObject(result.get())

    for i in range(100) :
        print formatObject(proxy.getBookUserIds([719791, 719827, 719844]))
    '''
    print time.time() - start

    #antispamService = client.getProxy('com.qunar.travel.antispam.service.IAntispamService')

    #print formatObject(antispamService.check([u'你好江泽民', u'64', u'呵呵']))

    #sortE = _model.Object('com.qunar.travel.query.param.SortDir', {'name' : 'DESC'})

    #print formatObject(proxy.getBookList('5763120@qunar', 0, 10, 1, sortE))

    #print proxy.getTravelBookDetail(692327L)

    #print proxy.clearCache(692327L)

    #proxy = client.getProxy('com.qunar.travel.destination.service.ITravelAlbumService', timeout = 3000)

    #print formatObject(proxy.findTravelAlbum(299914, 0, 10))
