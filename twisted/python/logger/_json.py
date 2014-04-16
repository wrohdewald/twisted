# -*- test-case-name: twisted.python.logger.test.test_json -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tools for saving and loading log events in a structured format.
"""

import types
from json import dumps, loads
from uuid import UUID

from ._flatten import flattenEvent
from ._file import FileLogObserver
from ._levels import LogLevel
from twisted.python.constants import NamedConstant

from twisted.python.compat import unicode
from twisted.python.failure import Failure



def failureAsJSON(obj):
    """
    Convert a L{Failure} to a JSON-serializable data structure.

    @return: a L{dict} of L{str} to ...  stuff, mostly reminiscent of
        L{Failure.__getstate__}
    """
    return dict(
        obj.__getstate__(),
        type=dict(
            __module__=obj.type.__module__,
            __name__=obj.type.__name__,
        )
    )



def nativify(x):
    """
    On Python 2, we really need native strings in a variety of places;
    attribute names will sort of work in a __dict__, but they're subtly wrong;
    however, printing tracebacks relies on I/O to containers that only support
    bytes.  This function converts _all_ native strings within a
    JSON-deserialized object to bytes.
    """
    if isinstance(x, list):
        return map(nativify, x)
    elif isinstance(x, dict):
        return dict((nativify(k), nativify(v)) for k, v in x.items())
    elif isinstance(x, unicode):
        return x.encode("utf-8")
    else:
        return x



def failureFromJSON(failureDict):
    """
    Load a L{Failure} from a dictionary deserialized from JSON.

    @param failureDict: a JSON-deserialized object like one previously returned
        by L{failureAsJSON}.
    @type failureDict: L{dict} mapping L{unicode} to attributes

    @return: L{Failure}
    @rtype: L{Failure}
    """
    newFailure = getattr(Failure, "__new__", None)
    if newFailure is None:
        failureDict = nativify(failureDict)
        f = types.InstanceType(Failure)
    else:
        f = newFailure(Failure)
    typeInfo = failureDict["type"]
    failureDict["type"] = type(typeInfo["__name__"], (), typeInfo)
    f.__dict__ = failureDict
    return f



classInfo = [
    (
        lambda level: (
            isinstance(level, NamedConstant) and
            getattr(LogLevel, level.name, None) is level
        ),
        UUID("02E59486-F24D-46AD-8224-3ACDF2A5732A"),
        lambda level: dict(name=level.name),
        lambda level: getattr(LogLevel, level["name"], None)
    ),

    (
        lambda o: isinstance(o, Failure),
        UUID("E76887E2-20ED-49BF-A8F8-BA25CC586F2D"),
        failureAsJSON, failureFromJSON
    ),
]



uuidToLoader = dict([
    (uuid, loader) for (predicate, uuid, saver, loader) in classInfo
])



def objectLoadHook(aDict):
    """
    Dictionary-to-object-translation hook for certain value types used within
    the logging system.

    @see: the C{object_hook} parameter to L{json.load}

    @param aDict: A dictionary loaded from a JSON object.
    @type aDict: L{dict}

    @return: L{aDict} itself, or the object represented by L{aDict}
    @rtype: L{object}
    """
    if "__class_uuid__" in aDict:
        return uuidToLoader[UUID(aDict["__class_uuid__"])](aDict)
    return aDict



def objectSaveHook(pythonObject):
    """
    Object-to-serializable hook for certain value types used within the logging
    system.

    @see: the C{default} parameter to L{json.dump}

    @param pythonObject: Any object.
    @type pythonObject: L{object}

    @return: If the object is one of the special types the logging system
        supports, a specially-formatted dictionary; otherwise, a marker
        dictionary indicating that it could not be serialized.
    """
    for (predicate, uuid, saver, loader) in classInfo:
        if predicate(pythonObject):
            result = saver(pythonObject)
            result["__class_uuid__"] = str(uuid)
            return result
    return {"unpersistable": True}



def eventAsJSON(event):
    """
    Encode an event as JSON, flattening it if necessary to preserve as much
    structure as possible.

    Not all structure from the log event will be preserved when it is
    serialized

    @param event: A log event dictionary.
    @type event: L{dict} with arbitrary keys and values

    @return: A string of the serialized JSON; note that this will contain no
        newline characters, and may thus safely be stored in a line-delimited
        file.
    @rtype: L{unicode}
    """
    if bytes is str:
        kw = dict(default=objectSaveHook, encoding="charmap", skipkeys=True)
    else:
        def default(unencodable):
            if isinstance(unencodable, bytes):
                return unencodable.decode("charmap")
            return objectSaveHook(unencodable)
        kw = dict(default=default, skipkeys=True)
    flattenEvent(event)
    result = dumps(event, **kw)
    if not isinstance(result, unicode):
        return unicode(result, "utf-8", "replace")
    return result



def eventFromJSON(eventText):
    """
    Decode a log event from JSON.

    @param eventText: The output of a previous call to L{eventAsJSON}
    @type eventText: L{unicode}

    @return: A reconstructed version of the log event.
    @rtype: L{dict}
    """
    loaded = loads(eventText, object_hook=objectLoadHook)
    return loaded



def jsonFileLogObserver(outFile):
    """
    Create a L{FileLogObserver} that emits JSON lines to a specified (writable)
    file-like object.

    @param outFile: A file-like object.  Ideally one should be passed which
        accepts L{unicode} data.  Otherwise, UTF-8 L{bytes} will be used.
    @type outFile: L{io.IOBase}

    @return: A file log observer.
    @rtype: L{FileLogObserver}
    """
    return FileLogObserver(outFile, lambda event: eventAsJSON(event) + u"\n")



def eventsFromJSONLogFile(inFile):
    """
    Load events from a file previously saved with L{jsonFileLogObserver}.

    @param inFile: A (readable) file-like object.  Data read from L{inFile}
        should be L{unicode} or UTF-8 L{bytes}.
    @type inFile: iterable of lines

    @return: Log events as read from C{inFile}.
    @rtype: iterable of L{dict}
    """
    for line in inFile:
        yield eventFromJSON(line)
