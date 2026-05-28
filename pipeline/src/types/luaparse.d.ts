declare module 'luaparse' {
  interface ParseOptions {
    luaVersion?: '5.1' | '5.2' | '5.3';
    encodingMode?: string;
  }
  interface Chunk { type: 'Chunk'; body: Statement[]; }
  type Statement = ReturnStatement | { type: string; [k: string]: unknown };
  interface ReturnStatement { type: 'ReturnStatement'; arguments: Expression[]; }
  type Expression =
    | TableConstructor | StringLiteral | NumericLiteral | BooleanLiteral
    | NilLiteral | UnaryExpression | Identifier | VarargLiteral
    | { type: string; [k: string]: unknown };
  interface TableConstructor { type: 'TableConstructor' | 'TableConstructorExpression'; fields: Field[]; }
  type Field = TableKeyString | TableKey | TableValue;
  interface TableKeyString { type: 'TableKeyString'; key: Identifier; value: Expression; }
  interface TableKey     { type: 'TableKey';     key: Expression;  value: Expression; }
  interface TableValue   { type: 'TableValue';   value: Expression; }
  interface StringLiteral  { type: 'StringLiteral';  value: string;  raw: string; }
  interface NumericLiteral { type: 'NumericLiteral'; value: number;  raw: string; }
  interface BooleanLiteral { type: 'BooleanLiteral'; value: boolean; }
  interface NilLiteral     { type: 'NilLiteral';     value: null; }
  interface VarargLiteral  { type: 'VarargLiteral';  value: string; }
  interface Identifier     { type: 'Identifier';     name: string; }
  interface UnaryExpression {
    type: 'UnaryExpression';
    operator: string;
    argument: Expression;
  }
  export function parse(code: string, opts?: ParseOptions): Chunk;
}
