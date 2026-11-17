"""Incrementally decode the first answer_markdown JSON string, not metadata."""
import re


class AnswerFieldStream:
    _HEADER = re.compile(r'\s*(?:```(?:json)?\s*)?\{\s*"answer_markdown"\s*:\s*"')
    _ESCAPES = {'"': '"', '\\': '\\', '/': '/', 'b': '\b', 'f': '\f',
                'n': '\n', 'r': '\r', 't': '\t'}

    def __init__(self):
        self.buffer = ""
        self.started = self.closed = self.disabled = False

    def feed(self, delta):
        if self.closed or self.disabled:
            return ""
        self.buffer += delta
        if not self.started:
            match = self._HEADER.match(self.buffer)
            if not match:
                # Different field order/format falls back to the final parser.
                if len(self.buffer) > 4096:
                    self.disabled, self.buffer = True, ""
                return ""
            self.started = True
            self.buffer = self.buffer[match.end():]
        out, i = [], 0
        while i < len(self.buffer):
            char = self.buffer[i]
            if char == '"':
                self.closed = True
                i += 1
                break
            if char != '\\':
                if ord(char) < 32:
                    raise ValueError("Unescaped control character in streamed JSON answer")
                out.append(char)
                i += 1
                continue
            if i + 1 >= len(self.buffer):
                break
            escaped = self.buffer[i + 1]
            if escaped in self._ESCAPES:
                out.append(self._ESCAPES[escaped])
                i += 2
                continue
            if escaped != 'u':
                raise ValueError("Invalid escape in streamed JSON answer")
            if i + 6 > len(self.buffer):
                break
            code = int(self.buffer[i + 2:i + 6], 16)
            width = 6
            if 0xD800 <= code <= 0xDBFF:
                if i + 12 > len(self.buffer):
                    break
                if self.buffer[i + 6:i + 8] != '\\u':
                    raise ValueError("Missing low surrogate in streamed JSON answer")
                low = int(self.buffer[i + 8:i + 12], 16)
                if not 0xDC00 <= low <= 0xDFFF:
                    raise ValueError("Invalid low surrogate in streamed JSON answer")
                code = 0x10000 + ((code - 0xD800) << 10) + low - 0xDC00
                width = 12
            elif 0xDC00 <= code <= 0xDFFF:
                raise ValueError("Unexpected low surrogate in streamed JSON answer")
            out.append(chr(code))
            i += width
        self.buffer = "" if self.closed else self.buffer[i:]
        return "".join(out)
