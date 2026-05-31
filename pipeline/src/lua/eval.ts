import * as luaparse from 'luaparse';
import { createRequire } from 'node:module';

export type LuaVal = string | number | boolean | null | LuaObj | LuaVal[];
export type LuaObj = { [key: string]: LuaVal };

// ── Static evaluator (fast, handles pure data tables) ─────────────────────────

export function evalLua(src: string): LuaVal {
  const ast = luaparse.parse(src, { luaVersion: '5.3' });

  const locals = new Map<string, LuaVal>();
  for (const stmt of ast.body) {
    if (stmt.type === 'LocalStatement') {
      const ls = stmt as unknown as {
        variables: Array<{ name: string }>;
        init: luaparse.Expression[];
      };
      for (let i = 0; i < ls.variables.length; i++) {
        const name = ls.variables[i].name;
        const initExpr = ls.init[i];
        if (initExpr) locals.set(name, evalExpr(initExpr, locals));
      }
    }
  }

  const ret = ast.body.find(n => n.type === 'ReturnStatement');
  if (!ret || ret.type !== 'ReturnStatement') return null;
  const r = ret as { type: 'ReturnStatement'; arguments: luaparse.Expression[] };
  return r.arguments.length ? evalExpr(r.arguments[0], locals) : null;
}

function parseStringRaw(raw: string): string {
  if (raw.startsWith('"') || raw.startsWith("'")) {
    return raw.slice(1, -1)
      .replace(/\\n/g, '\n').replace(/\\t/g, '\t').replace(/\\r/g, '\r')
      .replace(/\\"/g, '"').replace(/\\'/g, "'").replace(/\\\\/g, '\\');
  }
  const m = raw.match(/^\[=*\[([\s\S]*)\]=*\]$/);
  return m ? m[1].replace(/^\n/, '') : raw;
}

function evalExpr(node: luaparse.Expression, locals: Map<string, LuaVal>): LuaVal {
  switch (node.type) {
    case 'StringLiteral': {
      const s = node as luaparse.StringLiteral;
      return s.value !== null ? s.value : parseStringRaw(s.raw);
    }
    case 'NumericLiteral': return (node as luaparse.NumericLiteral).value;
    case 'BooleanLiteral': return (node as luaparse.BooleanLiteral).value;
    case 'NilLiteral':     return null;
    case 'VarargLiteral':  return null;
    case 'Identifier': {
      const name = (node as luaparse.Identifier).name;
      if (locals.has(name)) return locals.get(name)!;
      return name;
    }
    case 'UnaryExpression': {
      const u = node as luaparse.UnaryExpression;
      if (u.operator === '-') {
        const v = evalExpr(u.argument, locals);
        return typeof v === 'number' ? -v : null;
      }
      return null;
    }
    case 'TableConstructor':
    case 'TableConstructorExpression':
      return evalTable(node as luaparse.TableConstructor, locals);
    default: return null;
  }
}

function evalTable(node: luaparse.TableConstructor, locals: Map<string, LuaVal>): LuaObj | LuaVal[] {
  const obj: LuaObj = {};
  let arrayIdx = 1;
  for (const field of node.fields) {
    switch (field.type) {
      case 'TableKeyString': {
        const f = field as luaparse.TableKeyString;
        obj[f.key.name] = evalExpr(f.value, locals);
        break;
      }
      case 'TableKey': {
        const f = field as luaparse.TableKey;
        const k = evalExpr(f.key, locals);
        obj[String(k)] = evalExpr(f.value, locals);
        break;
      }
      case 'TableValue': {
        const f = field as luaparse.TableValue;
        obj[String(arrayIdx++)] = evalExpr(f.value, locals);
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

// ── Fengari runtime evaluator (handles functions, assignments, require) ───────
// Used as fallback when the static evaluator returns empty results.

const _require = createRequire(import.meta.url);

// Lua-side JSON serializer injected before capturing output
const _LUA_JSON_SERIALIZER = `
local function __json(v, d)
  d = (d or 0) + 1
  if d > 40 then return '"..."' end
  local t = type(v)
  if t == 'nil' then return 'null'
  elseif t == 'boolean' then return v and 'true' or 'false'
  elseif t == 'number' then
    if v ~= v then return 'null' end
    return string.format('%g', v)
  elseif t == 'string' then
    v = v:gsub('\\\\', '\\\\\\\\')
       :gsub('"',  '\\\\"')
       :gsub('\\n', '\\\\n')
       :gsub('\\r', '\\\\r')
       :gsub('\\t', '\\\\t')
    return '"' .. v .. '"'
  elseif t == 'table' then
    local parts = {}
    for k, val in pairs(v) do
      if type(k) == 'string' then
        table.insert(parts, __json(k) .. ':' .. __json(val, d))
      elseif type(k) == 'number' then
        table.insert(parts, '"' .. tostring(k) .. '":' .. __json(val, d))
      end
    end
    return '{' .. table.concat(parts, ',') .. '}'
  end
  return 'null'
end
`;

/**
 * @param src        Lua source of the module to evaluate
 * @param submodules Optional map of moduleName → Lua source for modules it requires via mw.loadData
 */
export function evalLuaRuntime(src: string, submodules?: Map<string, string>): LuaVal {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const fengari = _require('fengari') as any;
    const { lua, lauxlib, lualib, to_luastring, to_jsstring } = fengari;

    const L = lauxlib.luaL_newstate();
    lualib.luaL_openlibs(L);

    // Pre-register sub-modules so mw.loadData (→ require) can find them
    if (submodules?.size) {
      for (const [modName, modSrc] of submodules) {
        // Load the sub-module source and stash result as a global, then register via preload
        const subSrc = to_luastring(modSrc);
        if (lauxlib.luaL_loadbuffer(L, subSrc, subSrc.length, to_luastring(modName)) === lua.LUA_OK) {
          if (lua.lua_pcall(L, 0, 1, 0) === lua.LUA_OK) {
            // Stack: sub-module result. Wrap it in a preload function.
            // We use upvalues: store the table as an upvalue of the preload closure.
            lua.lua_pushcclosure(L, (Lx: unknown) => {
              // Push the upvalue (the pre-evaluated sub-module table)
              (lua as any).lua_pushvalue(Lx, (lua as any).lua_upvalueindex(1));
              return 1;
            }, 1);  // 1 upvalue (the module result on stack)
            const nameBytes = to_luastring('__sub_' + modName.replace(/[^a-zA-Z0-9]/g, '_'));
            lua.lua_setglobal(L, nameBytes);
            // Register in package.preload
            const escapedName = modName.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
            const globalRef = '__sub_' + modName.replace(/[^a-zA-Z0-9]/g, '_');
            lauxlib.luaL_dostring(L, to_luastring(
              `package.preload['${escapedName}'] = function() return ${globalRef} end`
            ));
          } else {
            lua.lua_pop(L, 1); // pop error
          }
        } else {
          lua.lua_pop(L, 1); // pop error
        }
      }
    }

    // Register stubs for common wiki utility modules used by data modules
    const registerStubs = `
      -- Module:Table — utility functions used by Void/data and others
      package.preload['Module:Table'] = function()
        return {
          size = function(t)
            local n = 0
            for _ in pairs(t) do n = n + 1 end
            return n
          end,
          merge = function(a, b)
            local r = {}
            for k,v in pairs(a) do r[k] = v end
            for k,v in pairs(b or {}) do r[k] = v end
            return r
          end,
          contains = function(t, val)
            for _,v in pairs(t) do if v == val then return true end end
            return false
          end,
          keys = function(t)
            local ks = {}
            for k in pairs(t) do ks[#ks+1] = k end
            return ks
          end,
          values = function(t)
            local vs = {}
            for _,v in pairs(t) do vs[#vs+1] = v end
            return vs
          end,
        }
      end
      -- Stub for other common wiki modules
      for _, m in ipairs({'Module:LuaSerializer','Module:String','Module:Math','Module:Shared'}) do
        package.preload[m] = function() return {} end
      end
      -- Stub the MediaWiki mw global used by some data modules
      mw = {
        site = { namespaces = { [828] = { name = "Module" } } },
        loadData = function(path) return require(path) end,
        text = { trim = function(s) return s and s:match("^%s*(.-)%s*$") or "" end },
        ustring = { lower = string.lower, upper = string.upper, len = string.len },
      }
      -- Catch-all require: any unregistered module returns empty table
      local _orig_require = require
      require = function(mod)
        local ok, r = pcall(_orig_require, mod)
        if ok and r then return r else return {} end
      end
    `;
    lauxlib.luaL_dostring(L, to_luastring(registerStubs));

    // Execute the module source, capture its return value
    const luaSrc = to_luastring(src);
    if (lauxlib.luaL_loadbuffer(L, luaSrc, luaSrc.length, to_luastring('chunk')) !== lua.LUA_OK) {
      const err = to_jsstring(lua.lua_tostring(L, -1) ?? to_luastring(''));
      process.stderr.write(`    [fengari] load error: ${err}\n`);
      lua.lua_close(L);
      return null;
    }
    if (lua.lua_pcall(L, 0, 1, 0) !== lua.LUA_OK) {
      const err = to_jsstring(lua.lua_tostring(L, -1) ?? to_luastring(''));
      process.stderr.write(`    [fengari] runtime error: ${err}\n`);
      lua.lua_close(L);
      return null;
    }

    // Stash result as global __result, inject serializer, run it
    lua.lua_setglobal(L, to_luastring('__result'));
    const serCode = _LUA_JSON_SERIALIZER + '\nreturn __json(__result)';
    if (lauxlib.luaL_dostring(L, to_luastring(serCode)) !== lua.LUA_OK) {
      lua.lua_close(L);
      return null;
    }

    const rawStr = lua.lua_tostring(L, -1);
    if (!rawStr) { lua.lua_close(L); return null; }
    const jsonStr = to_jsstring(rawStr);
    lua.lua_close(L);
    return JSON.parse(jsonStr) as LuaVal;
  } catch (err) {
    process.stderr.write(`    [fengari] error: ${(err as Error).message}\n`);
    return null;
  }
}

/** Returns true if a LuaVal is empty or contains only empty nested objects. */
export function isSubstantiallyEmpty(val: LuaVal): boolean {
  if (val === null || val === undefined) return true;
  if (typeof val !== 'object') return false;
  if (Array.isArray(val)) return (val as LuaVal[]).length === 0;
  const obj = val as LuaObj;
  const keys = Object.keys(obj);
  if (keys.length === 0) return true;
  return keys.every(k => isSubstantiallyEmpty(obj[k]));
}

/** Evaluate Lua source, falling back to the Fengari runtime for complex modules. */
export function evalLuaWithFallback(src: string, submodules?: Map<string, string>): LuaVal {
  const fast = evalLua(src);
  if (fast === null || isSubstantiallyEmpty(fast)) {
    return evalLuaRuntime(src, submodules);
  }
  return fast;
}
