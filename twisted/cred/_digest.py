# -*- test-case-name: twisted.test.test_digestauth -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Calculations for HTTP Digest authentication.

@see: U{http://www.faqs.org/rfcs/rfc2617.html}
"""

from twisted.python.compat import _PY3, unicode

from hashlib import md5, sha1

def updateHash(m, value):
    """
    I am a wrapper around m.update(value)
    If value is unicode, I encode it first
    as a utf-8 string
    """
    if isinstance(value, unicode):
        value = value.encode('utf-8')
    m.update(value)


# The digest math

algorithms = {
    'md5': md5,

    # md5-sess is more complicated than just another algorithm.  It requires
    # H(A1) state to be remembered from the first WWW-Authenticate challenge
    # issued and re-used to process any Authorization header in response to
    # that WWW-Authenticate challenge.  It is *not* correct to simply
    # recalculate H(A1) each time an Authorization header is received.  Read
    # RFC 2617, section 3.2.2.2 and do not try to make DigestCredentialFactory
    # support this unless you completely understand it. -exarkun
    'md5-sess': md5,

    'sha': sha1,
}

# DigestCalcHA1
def calcHA1(pszAlg, pszUserName, pszRealm, pszPassword, pszNonce, pszCNonce,
            preHA1=None):
    """
    Compute H(A1) from RFC 2617.

    @param pszAlg: The name of the algorithm to use to calculate the digest.
        Currently supported are md5, md5-sess, and sha.
    @param pszUserName: The username
    @param pszRealm: The realm
    @param pszPassword: The password
    @param pszNonce: The nonce
    @param pszCNonce: The cnonce

    @param preHA1: If available this is a str containing a previously
       calculated H(A1) as a hex string.  If this is given then the values for
       pszUserName, pszRealm, and pszPassword must be C{None} and are ignored.
    """

    if (preHA1 and (pszUserName or pszRealm or pszPassword)):
        raise TypeError(("preHA1 is incompatible with the pszUserName, "
                         "pszRealm, and pszPassword arguments"))

    if preHA1 is None:
        # We need to calculate the HA1 from the username:realm:password
        m = algorithms[pszAlg]()
        updateHash(m, pszUserName)
        updateHash(m, ":")
        updateHash(m, pszRealm)
        updateHash(m, ":")
        updateHash(m, pszPassword)
        HA1 = m.digest()
    else:
        # We were given a username:realm:password
        HA1 = preHA1.decode('hex')

    if pszAlg == "md5-sess":
        m = algorithms[pszAlg]()
        updateHash(m, HA1)
        updateHash(m, ":")
        updateHash(m, pszNonce)
        updateHash(m, ":")
        updateHash(m, pszCNonce)
        HA1 = m.digest()

    return HA1.encode('hex')


def calcHA2(algo, pszMethod, pszDigestUri, pszQop, pszHEntity):
    """
    Compute H(A2) from RFC 2617.

    @param pszAlg: The name of the algorithm to use to calculate the digest.
        Currently supported are md5, md5-sess, and sha.
    @param pszMethod: The request method.
    @param pszDigestUri: The request URI.
    @param pszQop: The Quality-of-Protection value.
    @param pszHEntity: The hash of the entity body or C{None} if C{pszQop} is
        not C{'auth-int'}.
    @return: The hash of the A2 value for the calculation of the response
        digest.
    """
    m = algorithms[algo]()
    updateHash(m, pszMethod)
    updateHash(m, ":")
    updateHash(m, pszDigestUri)
    if pszQop == "auth-int":
        updateHash(m, ":")
        updateHash(m, pszHEntity)
    return m.digest().encode('hex')


def calcResponse(HA1, HA2, algo, pszNonce, pszNonceCount, pszCNonce, pszQop):
    """
    Compute the digest for the given parameters.

    @param HA1: The H(A1) value, as computed by L{calcHA1}.
    @param HA2: The H(A2) value, as computed by L{calcHA2}.
    @param pszNonce: The challenge nonce.
    @param pszNonceCount: The (client) nonce count value for this response.
    @param pszCNonce: The client nonce.
    @param pszQop: The Quality-of-Protection value.
    """
    m = algorithms[algo]()
    updateHash(m, HA1)
    updateHash(m, ":")
    updateHash(m, pszNonce)
    updateHash(m, ":")
    if pszNonceCount and pszCNonce:
        updateHash(m, pszNonceCount)
        updateHash(m, ":")
        updateHash(m, pszCNonce)
        updateHash(m, ":")
        updateHash(m, pszQop)
        updateHash(m, ":")
    updateHash(m, HA2)
    respHash = m.digest().encode('hex')
    return respHash
