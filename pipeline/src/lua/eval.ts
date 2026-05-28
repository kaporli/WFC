import * as luaparse from 'luaparse';

export type LuaVal = string | number | boolean | null | LuaObj | LuaVal[];
export type LuaObj = { [key: string]: LuaVal };

export function evalLua(src: string): LuaVal {
  const ast = luaparse.parse(src, { luaVersion: '5.3' });
  const ret = ast.body.find(n => n.type === 'ReturnStatement');
  if (!ret || ret.type !== 'ReturnStatement') return null;
  const r = ret as { type: 'ReturnStatement'; arguments: luaparse.Expression[] };
  return r.arguments.length ? evalExpr(r.arguments[0]) : null;
}

/** luaparse may return null for StringLiteral.value; derive it from raw instead. */
function parseStringRaw(raw: string): string {
  // Strip surrounding quotes (single, double, or long-string brackets)
  if (raw.startsWith('"') || raw.startsWith("'")) {
    return raw.slice(1, -1)
      .replace(/\\n/g, '\n').replace(/\\t/g, '\t').replace(/\\r/g, '\r')
      .replace(/\\"/g, '"').replace(/\\'/g, "'").replace(/\\\\/g, '\\');
  }
  // Long string [[ ... ]] or [=[ ... ]=]
  const m = raw.match(/^\[=*\[([\s\S]*)\]=*\]$/);
  return m ? m[1].replace(/^\n/, '') : raw;
}

function evalExpr(node: luaparse.Expression): LuaVal {
  switch (node.type) {
    case 'StringLiteral': {
      const s = node as luaparse.StringLiteral;
      return s.value !== null ? s.value : parseStringRaw(s.raw);
    }
    case 'NumericLiteral': return (node as luaparse.NumericLiteral).value;
    case 'BooleanLiteral': return (node as luaparse.BooleanLiteral).value;
    case 'NilLiteral':     return null;
    case 'VarargLiteral':  return null;
    case 'Identifier':     return (node as luaparse.Identifier).name;
    case 'UnaryExpression': {
      const u = node as luaparse.UnaryExpression;
      if (u.operator === '-') {
        const v = evalExpr(u.argument);
        return typeof v === 'number' ? -v : null;
      }
      return null;
    }
    case 'TableConstructor':
    case 'TableConstructorExpression':
      return evalTable(node as luaparse.TableConstructor);
    default: return null;
  }
}

function evalTable(node: luaparse.TableConstructor): LuaObj | LuaVal[] {
  const obj: LuaObj = {};
  let arrayIdx = 1;

  for (const field of node.fields) {
    switch (field.type) {
      case 'TableKeyString': {
        const f = field as luaparse.TableKeyString;
        obj[f.key.name] = evalExpr(f.value);
        break;
      }
      case 'TableKey': {
        const f = field as luaparse.TableKey;
        const k = evalExpr(f.key);
        obj[String(k)] = evalExpr(f.value);
        break;
      }
      case 'TableValue': {
        const f = field as luaparse.TableValue;
        obj[String(arrayIdx++)] = evalExpr(f.value);
        break;
      }
    }
  }

  const keys = Object.keys(obj);
  if (keys.length > 0 && keys.every((k, i) => k === String(i + 1))) {
    return keys.map(k => obj[k]);
  }
  return obj;
}
