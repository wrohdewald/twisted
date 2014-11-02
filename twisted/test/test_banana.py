# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from __future__ import division, absolute_import

import StringIO
from twisted.python.compat import _PY3, long

import sys
from functools import partial

from itertools import chain

# Twisted Imports
from twisted.trial import unittest
from twisted.spread import banana
from twisted.python import failure
from twisted.python.compat import networkChar
from twisted.internet import protocol, main
from twisted.test.proto_helpers import StringTransport


class MathTestCase(unittest.TestCase):
    def test_int2b128(self):
        funkylist = chain(range(0,100), range(1000,1100), range(1000000,1000100), [1024 **10,])
        for i in funkylist:
            x = StringIO.StringIO()
            banana.int2b128(i, x.write)
            v = x.getvalue()
            y = banana.b1282int(v)
            assert y == i, "y = %s; i = %s" % (y,i)



def selectDialect(protocol, dialect):
    """
    Dictate a Banana dialect to use.

    @param protocol: A L{banana.Banana} instance which has not yet had a
        dialect negotiated.

    @param dialect: A L{bytes} instance naming a Banana dialect to select.
    """
    # We can't do this the normal way by delivering bytes because other setup
    # stuff gets in the way (for example, clients and servers have incompatible
    # negotiations for this step).  So use the private API to make this happen.
    protocol._selectDialect(dialect)



def encode(bananaFactory, obj):
    """
    Banana encode an object using L{banana.Banana.sendEncoded}.

    @param bananaFactory: A no-argument callable which will return a new,
        unconnected protocol instance to use to do the encoding (this should
        most likely be a L{banana.Banana} instance).

    @param obj: The object to encode.
    @type obj: Any type supported by Banana.

    @return: A L{bytes} instance giving the encoded form of C{obj}.
    """
    transport = StringTransport()
    banana = bananaFactory()
    banana.makeConnection(transport)
    transport.clear()

    banana.sendEncoded(obj)
    return transport.value()



class BananaTestBase(unittest.TestCase):
    """
    The base for test classes. It defines commonly used things and sets up a
    connection for testing.
    """
    encClass = banana.Banana

    def setUp(self):
        """
        The default test environment is for a client
        """
        self._setUp(isClient=True)


    def _setUp(self, isClient=True):
        """
        Prepare the test environment.

        @param isClient: The role that self.enc (banana.Banana) should take.
        """
        self.io = StringIO.StringIO()
        self.enc = self.encClass(isClient)
        self.enc.makeConnection(protocol.FileWrapper(self.io))
        selectDialect(self.enc, b"none")
        self.enc.expressionReceived = self.putResult
        self.encode = partial(encode, self.encClass)


    def putResult(self, result):
        """
        Store an expression received by C{self.enc}.

        @param result: The object that was received.
        @type result: Any type supported by Banana.
        """
        self.result = result


    def tearDown(self):
        self.enc.connectionLost(failure.Failure(main.CONNECTION_DONE))
        del self.enc




class BananaTestCase(BananaTestBase):
    """
    General banana tests.
    """

    def test_string(self):
        """
        Sending and receiving a byte string must not change it
        """
        foo = b'hello'
        self.enc.sendEncoded(foo)
        l = []
        self.enc.dataReceived(self.io.getvalue())
        assert self.result == foo, "%s!=%s" % (repr(self.result), repr(foo))


    def test_unsupportedUnicode(self):
        """
        Banana does not support unicode.  ``Banana.sendEncoded`` raises
        ``BananaError`` if called with an instance of ``unicode``.
        """
        self._unsupportedTypeTest(u"hello", "__builtin__.unicode")


    def test_unsupportedBuiltinType(self):
        """
        Banana does not support arbitrary builtin types like L{type}.
        L{banana.Banana.sendEncoded} raises L{banana.BananaError} if called
        with an instance of L{type}.
        """
        # type is an instance of type
        self._unsupportedTypeTest(type, "__builtin__.type")


    def test_unsupportedUserType(self):
        """
        Banana does not support arbitrary user-defined types (such as those
        defined with the ``class`` statement).  ``Banana.sendEncoded`` raises
        ``BananaError`` if called with an instance of such a type.
        """
        self._unsupportedTypeTest(MathTestCase(), __name__ + ".MathTestCase")


    def _unsupportedTypeTest(self, obj, name):
        """
        Assert that L{banana.Banana.sendEncoded} raises L{banana.BananaError}
        if called with the given object.

        @param obj: Some object that Banana does not support.
        @param name: The name of the type of the object.

        @raise: The failure exception is raised if L{Banana.sendEncoded} does
            not raise L{banana.BananaError} or if the message associated with the
            exception is not formatted to include the type of the unsupported
            object.
        """
        exc = self.assertRaises(banana.BananaError, self.enc.sendEncoded, obj)
        self.assertIn("Banana cannot send {0} objects".format(name), str(exc))


    def test_connectServer(self):
        """
        When a client connects to a Banana server, the Banana server
        sends it an encoded list of supported dialects.
        """
        self.dataFromServer = None
        def serverSendEncoded(s):
            self.dataFromServer = s
        self._setUp(isClient=False)
        # catch answer from server
        clientSendEncoded = self.enc.sendEncoded
        self.enc.sendEncoded = serverSendEncoded
        self.enc.makeConnection(protocol.FileWrapper(self.io))
        self.assertEqual(self.dataFromServer, [b'pb', b'none'])


    def test_noExpressionReceivedHook(self):
        """
        The implementation for a dialect other than 'none' must
        override Banana.expressionReceived with a dialect specific
        implementation.
        Otherwise Banana.expressionReceived will raise NotImplementedError.
        """
        # setUp did just that
        self.assertTrue(self.enc.expressionReceived)
        # now we don't
        self.assertRaises(NotImplementedError,
            self.encClass().expressionReceived, b'x')


    def test_clientSelectsWrongDialect(self):
        """
        The client must select one of the dialects offered by the server.
        Otherwise the server closes the connection.
        """
        self._setUp(isClient=False)
        self.enc.currentDialect = None
        self.enc.sendEncoded(b'abc') # client sends abc to server
        self.enc.dataReceived(self.io.getvalue())
        self.assertTrue(self.io.closed) # if server gets back wrong dialect, it closes
        self.assertEqual(getattr(self, 'result', 'NO_RESULT'), 'NO_RESULT')


    def test_clientSupportNoDialect(self):
        """
        If the client gets only unimplemented dialects from the server,
        it leaves currentDialect as None and closes the connection.
        """
        self.assertTrue(self.enc.isClient)
        self.enc.currentDialect = None
        self.enc.sendEncoded([b'px'])
        self.enc.dataReceived(self.io.getvalue())
        self.assertIs(self.enc.currentDialect, None)
        self.assertTrue(self.io.closed)


    def test_clientSelectsCorrectDialect(self):
        """
        The client selects one of the dialects offered by the server
        and returns its choice to the server. This test is for the
        server side receiving the correct selection.
        """
        self._setUp(isClient=False)
        self.enc.currentDialect = None
        self.enc.sendEncoded(b'pb') # client sends dialect pb to server
        self.enc.dataReceived(self.io.getvalue())
        # server sets the dialect selected by client
        self.assertEqual(b'pb', self.enc.currentDialect)
        # server does not further process the received message
        self.assertEqual(getattr(self, 'result', 'NO_RESULT'), 'NO_RESULT')


    def test_startWithRightDialect(self):
        """
        The client selects the first offered dialect which is implemented
        and returns it to the server. This test is for the client side
        selecting the correct dialect.
        """
        self.dataFromClient = None
        def sendEncoded(s):
            self.dataFromClient = s
        self.enc.currentDialect = None
        self.enc.sendEncoded([b'abc', b'pb', b'def'])
        self.enc.sendEncoded = sendEncoded
        # dataReceived chooses one of the received dialects and returns it
        # by calling sendEncoded
        self.enc.dataReceived(self.io.getvalue())
        self.assertEqual(self.dataFromClient, b'pb')
        self.assertEqual(self.enc.currentDialect, b'pb')


    def test_bytes(self):
        """
        Sending and receiving a byte string must not change it
        """
        foo = b'hello'
        self.enc.sendEncoded(foo)
        self.enc.dataReceived(self.io.getvalue())
        self.assertEqual(self.result, foo)


    def test_int(self):
        """
        A positive integer less than 2 ** 32 should round-trip through
        banana without changing value and should come out represented
        as an C{int} (regardless of the type which was encoded).
        """
        for value in (10151, long(10151)):
            self.enc.sendEncoded(value)
            self.enc.dataReceived(self.io.getvalue())
            self.assertEqual(self.result, 10151)
            self.assertIsInstance(self.result, int)


    def test_couldNotSend(self):
        """
        Only a few basic types are sendable. For others,
        Banana raises BananaError.
        """
        self.assertRaises(banana.BananaError, self.enc.sendEncoded, BananaTestCase)


    def test_encodeTooLargeStr(self):
        """
        Strings have a maximum length. If too long, Banana.sendEncoded raises
        BananaError.
        """
        data = b'a' * (banana.SIZE_LIMIT)
        self.enc.sendEncoded(data)
        data = b'a' * (banana.SIZE_LIMIT+1)
        self.assertRaises(banana.BananaError, self.enc.sendEncoded, data)


    def test_encodeTooLargeList(self):
        """
        Lists have a maximum length. If too long, Banana.sendEncoded raises
        BananaError.
        """
        # data = list(b'a' * (banana.SIZE_LIMIT)) This takes 4 seconds, not important
        # self.enc.sendEncoded(data)
        data = list(b'a' * (banana.SIZE_LIMIT+1))
        self.assertRaises(banana.BananaError, self.enc.sendEncoded, data)


    def test_largeLong(self):
        """
        Integers greater than 2 ** 32 and less than -2 ** 32 should
        round-trip through banana without changing value and should
        come out represented as C{int} instances if the value fits
        into that type on the receiving platform.
        """
        for exp in (32, 64, 128, 256):
            for add in (0, 1):
                m = 2 ** exp + add
                for n in (m, -m-1):
                    self.enc.dataReceived(self.encode(n))
                    self.assertEqual(self.result, n)
                    if _PY3:
                        # does not know long
                        self.assertIsInstance(self.result, int)
                    else:
                        if n > sys.maxint or n < -sys.maxint - 1:
                            self.assertIsInstance(self.result, long)
                        else:
                            self.assertIsInstance(self.result, int)


    def _getSmallest(self):
        # How many bytes of prefix our implementation allows
        bytes = self.enc.prefixLimit
        # How many useful bits we can extract from that based on Banana's
        # base-128 representation.
        bits = bytes * 7
        # The largest number we _should_ be able to encode
        largest = 2 ** bits - 1
        # The smallest number we _shouldn't_ be able to encode
        smallest = largest + 1
        return smallest


    def test_encodeTooLargeLong(self):
        """
        Test that a long above the implementation-specific limit is rejected
        as too large to be encoded.
        """
        smallest = self._getSmallest()
        self.assertRaises(banana.BananaError, self.enc.sendEncoded, smallest)


    def test_decodeTooLargePrefix(self):
        """
        The size of the prefix has a maximum. If too long,
        Banana.dataReceived raises BananaError.
        """
        oldLimit = self.enc.prefixLimit
        try:
            self.enc.setPrefixLimit(13)
            data = b'x' * 13
            self.enc.dataReceived(data)
            data = b'x' * 14
            self.assertRaises(banana.BananaError, self.enc.dataReceived, data)
        finally:
            self.enc.setPrefixLimit(oldLimit)


    def test_decodeTooLargeLong(self):
        """
        Test that a long above the implementation specific limit is rejected
        as too large to be decoded.
        """
        smallest = self._getSmallest()
        self.enc.setPrefixLimit(self.enc.prefixLimit * 2)
        self.enc.sendEncoded(smallest)
        encoded = self.io.getvalue()
        self.io.truncate(0)
        self.enc.setPrefixLimit(self.enc.prefixLimit // 2)

        self.assertRaises(banana.BananaError, self.enc.dataReceived, encoded)


    def _getLargest(self):
        return -self._getSmallest()


    def test_encodeTooSmallLong(self):
        """
        Test that a negative long below the implementation-specific limit is
        rejected as too small to be encoded.
        """
        largest = self._getLargest()
        self.assertRaises(banana.BananaError, self.enc.sendEncoded, largest)


    def test_decodeTooSmallLong(self):
        """
        Test that a negative long below the implementation specific limit is
        rejected as too small to be decoded.
        """
        largest = self._getLargest()
        self.enc.setPrefixLimit(self.enc.prefixLimit * 2)
        self.enc.sendEncoded(largest)
        encoded = self.io.getvalue()
        self.io.truncate(0)
        self.enc.setPrefixLimit(self.enc.prefixLimit // 2)

        self.assertRaises(banana.BananaError, self.enc.dataReceived, encoded)


    def test_negativeLong(self):
        self.enc.sendEncoded(long(-1015))
        self.enc.dataReceived(self.io.getvalue())
        assert self.result == long(-1015), "should be long(-1015), got %s" % self.result

    def test_integer(self):
        self.enc.sendEncoded(1015)
        self.enc.dataReceived(self.io.getvalue())
        assert self.result == 1015, "should be 1015, got %s" % self.result

    def test_negative(self):
        self.enc.sendEncoded(-1015)
        self.enc.dataReceived(self.io.getvalue())
        assert self.result == -1015, "should be -1015, got %s" % self.result

    def test_float(self):
        self.enc.sendEncoded(1015.)
        self.enc.dataReceived(self.io.getvalue())
        assert self.result == 1015.

    def test_list(self):
        foo = [1, 2, [3, 4], [30.5, 40.2], 5, [b"six", b"seven", [b"eight", 9]], [10], []]
        self.enc.sendEncoded(foo)
        self.enc.dataReceived(self.io.getvalue())
        assert self.result == foo, "%s!=%s" % (repr(self.result), repr(foo))

    def test_partial(self):
        """
        Test feeding the data byte per byte to the receiver. Normally
        data is not split.
        """
        maxint = sys.maxsize if _PY3 else sys.maxint
        foo = [1, 2, [3, 4], [30.5, 40.2], 5,
               [b"six", b"seven", [b"eight", 9]], [10],
               # TODO: currently the C implementation's a bit buggy...
               maxint * long(3), maxint * long(2), maxint * long(-2)]
        self.enc.sendEncoded(foo)
        self.feed(self.io.getvalue())
        assert self.result == foo, "%s!=%s" % (repr(self.result), repr(foo))


    def feed(self, data):
        """
        Feed the data byte per byte to the receiver.

        @param data: The bytes to deliver.
        @type data: L{bytes}
        """
        for byte in data:
            self.enc.dataReceived(byte)


    def test_oversizedList(self):
        data = b'\x02\x01\x01\x01\x01\x80'
        # list(size=0x0101010102, about 4.3e9)
        self.failUnlessRaises(banana.BananaError, self.feed, data)

    def test_oversizedString(self):
        data = b'\x02\x01\x01\x01\x01\x82'
        # string(size=0x0101010102, about 4.3e9)
        self.failUnlessRaises(banana.BananaError, self.feed, data)

    def test_crashString(self):
        crashString = b'\x00\x00\x00\x00\x04\x80'
        # string(size=0x0400000000, about 17.2e9)

        #  cBanana would fold that into a 32-bit 'int', then try to allocate
        #  a list with PyList_New(). cBanana ignored the NULL return value,
        #  so it would segfault when trying to free the imaginary list.

        # This variant doesn't segfault straight out in my environment.
        # Instead, it takes up large amounts of CPU and memory...
        #crashString = b'\x00\x00\x00\x00\x01\x80'
        # print repr(crashString)
        #self.failUnlessRaises(Exception, self.enc.dataReceived, crashString)
        try:
            # should now raise MemoryError
            self.enc.dataReceived(crashString)
        except banana.BananaError:
            pass

    def test_crashNegativeLong(self):
        # There was a bug in cBanana which relied on negating a negative integer
        # always giving a positive result, but for the lowest possible number in
        # 2s-complement arithmetic, that's not true, i.e.
        #     long x = -2147483648;
        #     long y = -x;
        #     x == y;  /* true! */
        # (assuming 32-bit longs)
        self.enc.sendEncoded(-2147483648)
        self.enc.dataReceived(self.io.getvalue())
        assert self.result == -2147483648, "should be -2147483648, got %s" % self.result


    def test_sizedIntegerTypes(self):
        """
        Test that integers below the maximum C{INT} token size cutoff are
        serialized as C{INT} or C{NEG} and that larger integers are
        serialized as C{LONGINT} or C{LONGNEG}.
        """
        baseIntIn = +2147483647
        baseNegIn = -2147483648

        baseIntOut = b'\x7f\x7f\x7f\x07\x81'
        self.assertEqual(self.encode(baseIntIn - 2), b'\x7d' + baseIntOut)
        self.assertEqual(self.encode(baseIntIn - 1), b'\x7e' + baseIntOut)
        self.assertEqual(self.encode(baseIntIn - 0), b'\x7f' + baseIntOut)

        baseLongIntOut = b'\x00\x00\x00\x08\x85'
        self.assertEqual(self.encode(baseIntIn + 1), b'\x00' + baseLongIntOut)
        self.assertEqual(self.encode(baseIntIn + 2), b'\x01' + baseLongIntOut)
        self.assertEqual(self.encode(baseIntIn + 3), b'\x02' + baseLongIntOut)

        baseNegOut = b'\x7f\x7f\x7f\x07\x83'
        self.assertEqual(self.encode(baseNegIn + 2), b'\x7e' + baseNegOut)
        self.assertEqual(self.encode(baseNegIn + 1), b'\x7f' + baseNegOut)
        self.assertEqual(self.encode(baseNegIn + 0), b'\x00\x00\x00\x00\x08\x83')

        baseLongNegOut = b'\x00\x00\x00\x08\x86'
        self.assertEqual(self.encode(baseNegIn - 1), b'\x01' + baseLongNegOut)
        self.assertEqual(self.encode(baseNegIn - 2), b'\x02' + baseLongNegOut)
        self.assertEqual(self.encode(baseNegIn - 3), b'\x03' + baseLongNegOut)



class DialectTests(BananaTestBase):
    """
    Tests for Banana's handling of dialects.
    """
    vocab = b'remote'
    legalPbItem = networkChar(banana.Banana.outgoingVocabulary[vocab]) + banana.VOCAB
    illegalPbItem = networkChar(122) + banana.VOCAB

    def test_dialectNotSet(self):
        """
        If no dialect has been selected and a PB VOCAB item is received,
        L{NotImplementedError} is raised.
        """
        self.assertRaises(
            NotImplementedError,
            self.enc.dataReceived, self.legalPbItem)


    def test_receivePb(self):
        """
        If the PB dialect has been selected, a PB VOCAB item is accepted.
        """
        selectDialect(self.enc, b'pb')
        self.enc.dataReceived(self.legalPbItem)
        self.assertEqual(self.result, self.vocab)


    def test_receiveIllegalPb(self):
        """
        If the PB dialect has been selected and an unrecognized PB VOCAB item
        is received, L{banana.Banana.dataReceived} raises L{KeyError}.
        """
        selectDialect(self.enc, b'pb')
        self.assertRaises(KeyError, self.enc.dataReceived, self.illegalPbItem)


    def test_sendPb(self):
        """
        if pb dialect is selected, the sender must be able to send things in
        that dialect.
        """
        selectDialect(self.enc, b'pb')
        self.enc.sendEncoded(self.vocab)
        self.assertEqual(self.legalPbItem, self.io.getvalue())



class GlobalCoderTests(unittest.TestCase):
    """
    Tests for the free functions L{banana.encode} and L{banana.decode}.
    """
    def test_statelessDecode(self):
        """
        Calls to L{banana.decode} are independent of each other.
        """
        # Banana encoding of 2 ** 449
        undecodable = b'\x7f' * 65 + b'\x85'
        self.assertRaises(banana.BananaError, banana.decode, undecodable)

        # Banana encoding of 1.  This should be decodable even though the
        # previous call passed un-decodable data and triggered an exception.
        decodable = b'\x01\x81'
        self.assertEqual(banana.decode(decodable), 1)
        self.assertEqual(banana.encode(1), decodable)
