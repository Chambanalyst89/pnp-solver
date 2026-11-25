"""Check a circuit against the edge function on all inputs. Does not use the SAT encoding."""


def verify_circuit(n, edges, mode, k, circuit):
    """Return None if the circuit is correct, otherwise a description of the fault."""
    if len(circuit) != k:
        return f"has {len(circuit)} gates, expected {k}"
    nots = 0
    for g, (op, a, b) in enumerate(circuit):
        if op not in ("and", "or", "not"):
            return f"gate {g} has unknown op {op!r}"
        if not (0 <= a < n + g and 0 <= b < n + g):
            return f"gate {g} reads a wire that is not earlier"
        nots += op == "not"
    if nots > (1 if mode == "not" else 0):
        return f"{nots} NOT gates in mode {mode}"
    for x in range(1 << n):
        wires = [bool((x >> i) & 1) for i in range(n)]
        for op, a, b in circuit:
            if op == "and":
                wires.append(wires[a] and wires[b])
            elif op == "or":
                wires.append(wires[a] or wires[b])
            else:
                wires.append(not wires[a])
        expected = any(wires[u] and wires[v] for u, v in edges)
        if wires[-1] != expected:
            return f"wrong output on input {x:0{n}b} (vertex 0 is the rightmost bit)"
    return None
