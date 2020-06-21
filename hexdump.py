__python3__ = True


def ordp(c):
    """
    Helper that returns a printable binary data representation.
    """
    output = []

    if __python3__:
        for i in c:
            if (i < 32) or (i >= 127):
                output.append('.')
            else:
                output.append(chr(i))
    else:
        for i in c:
            j = ord(i)
            if (j < 32) or (j >= 127):
                output.append('.')
            else:
                output.append(i)

    return ''.join(output)


def hexdump(p, max_length=None):
    """
    Return a hexdump representation of binary data.
    Usage:
    >>> from hexdump import hexdump
    >>> print(hexdump(
    ...     b'\\x00\\x01\\x43\\x41\\x46\\x45\\x43\\x41\\x46\\x45\\x00\\x01'
    ... ))
    0000   00 01 43 41 46 45 43 41  46 45 00 01               ..CAFECAFE..
    """
    output = []
    l = len(p)
    if max_length is not None:
        l = min(l, max_length)
    i = 0
    while i < l:
        output.append('%04d   ' % i)
        for j in range(16):
            if (i + j) < l:
                output.append('%02x ' % p[i + j])
            else:
                output.append('   ')
            if (j % 16) == 7:
                output.append(' ')
        output.append('  ')
        output.append(ordp(p[i:i + 16]))
        output.append('\n')
        i += 16
    print(''.join(output).rstrip('\n'))
