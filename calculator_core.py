"""Calculator state machine — no GUI imports (safe for WSGI / headless servers)."""


class CalculatorState:
    __slots__ = ("display", "stored", "pending_op", "fresh")

    def __init__(self) -> None:
        self.display = "0"
        self.stored: float | None = None
        self.pending_op: str | None = None
        self.fresh = True

    def dispatch(self, key: str, kind: str) -> None:
        if kind == "num":
            self._input_digit(key)
        elif kind == "op":
            self._input_op(key)
        elif kind == "eq":
            self._equals()
        elif kind == "clear":
            self._clear()
        elif kind == "back":
            self._backspace()

    def _read_display(self) -> str:
        return self.display

    def _set_display(self, value: str) -> None:
        v = value or "0"
        if len(v) > 14:
            try:
                n = float(v)
                v = f"{n:.6g}"
            except ValueError:
                v = v[:14]
        self.display = v or "0"

    def _input_digit(self, d: str) -> None:
        cur = self._read_display()
        if cur == "Error":
            cur = "0"

        if self.fresh:
            self.fresh = False
            if d == ".":
                self._set_display("0.")
            else:
                self._set_display(d)
            return

        if d == ".":
            if "." in cur:
                return
            self._set_display(cur + ".")
        elif cur == "0":
            self._set_display(d)
        else:
            self._set_display(cur + d)

    def _apply_op(self, a: float, b: float, op: str) -> float:
        if op == "+":
            return a + b
        if op == "−":
            return a - b
        if op == "×":
            return a * b
        if op == "÷":
            if b == 0:
                raise ZeroDivisionError
            return a / b
        return b

    def _input_op(self, op: str) -> None:
        try:
            current = float(self._read_display())
        except ValueError:
            self._clear()
            return

        if self.stored is not None and self.pending_op and not self.fresh:
            try:
                result = self._apply_op(self.stored, current, self.pending_op)
            except ZeroDivisionError:
                self._set_display("Error")
                self._reset_state()
                return
            self.stored = result
            self._set_display(self._format(result))
        else:
            self.stored = current

        self.pending_op = op
        self.fresh = True

    def _equals(self) -> None:
        if self.pending_op is None or self.stored is None:
            return
        try:
            current = float(self._read_display())
        except ValueError:
            self._clear()
            return

        try:
            result = self._apply_op(self.stored, current, self.pending_op)
        except ZeroDivisionError:
            self._set_display("Error")
            self._reset_state()
            return

        self._set_display(self._format(result))
        self._reset_state()
        self.stored = result

    def _format(self, n: float) -> str:
        if abs(n) >= 1e12 or (abs(n) < 1e-9 and n != 0):
            return f"{n:.6g}"
        if n == int(n):
            return str(int(n))
        s = f"{n:.10f}".rstrip("0").rstrip(".")
        return s if s else "0"

    def _clear(self) -> None:
        self._set_display("0")
        self._reset_state()

    def _reset_state(self) -> None:
        self.stored = None
        self.pending_op = None
        self.fresh = True

    def _backspace(self) -> None:
        if self.fresh:
            return
        cur = self._read_display()
        if len(cur) <= 1 or cur in ("Error",):
            self._set_display("0")
            self.fresh = True
            return
        self._set_display(cur[:-1])

    @classmethod
    def from_form(cls, form: dict[str, str]) -> "CalculatorState":
        s = cls()
        s.display = (form.get("display") or "0")[:64]
        raw_st = (form.get("stored") or "").strip()
        if raw_st:
            try:
                s.stored = float(raw_st)
            except ValueError:
                s.stored = None
        else:
            s.stored = None
        po = (form.get("pending_op") or "").strip()
        s.pending_op = po if po else None
        s.fresh = (form.get("fresh") or "0") in ("1", "true", "True", "on")
        return s
