"""Core constructs for PostgreSQL utility statements unsupported by built-in Core."""

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ClauseElement, Executable


class ProcedureCall(Executable, ClauseElement):
    inherit_cache = False

    def __init__(self, schema, name, arguments):
        self.schema, self.name, self.arguments = schema, name, arguments


@compiles(ProcedureCall, "postgresql")
def compile_call(element, compiler, **kw):
    name = (
        compiler.preparer.quote_schema(element.schema) + "." + compiler.preparer.quote(element.name)
    )
    arguments = ", ".join(compiler.process(arg, **kw) for arg in element.arguments)
    return f"CALL {name}({arguments})"
