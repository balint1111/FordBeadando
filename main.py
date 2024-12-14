import ply.lex as lex
import ply.yacc as yacc
import re
import json
from typing import Optional, Any, Dict, List, Tuple, Union

# Define tokens
tokens: Tuple[str, ...] = (
    'LBRACKET', 'RBRACKET', 'LBRACE', 'RBRACE',
    'COLON', 'COMMA',
    'STRING', 'NUMBER',
    'TRUE', 'FALSE', 'NULL',
)

# Token definitions
t_LBRACKET: str = r'\['
t_RBRACKET: str = r'\]'
t_LBRACE: str = r'\{'
t_RBRACE: str = r'\}'
t_COLON: str = r':'
t_COMMA: str = r','

def t_TRUE(t: lex.LexToken) -> lex.LexToken:
    r'true'
    t.value = True
    return t

def t_FALSE(t: lex.LexToken) -> lex.LexToken:
    r'false'
    t.value = False
    return t

def t_NULL(t: lex.LexToken) -> lex.LexToken:
    r'null'
    t.value = None
    return t

def t_STRING(t: lex.LexToken) -> lex.LexToken:
    r'"([^"\\]|\\["\\/bfnrt]|\\u[0-9a-fA-F]{4})*"'
    t.value = t.value[1:-1]  # Remove quotes
    return t

def t_NUMBER(t: lex.LexToken) -> lex.LexToken:
    r'-?\d+(\.\d+)?([eE][+-]?\d+)?'
    if '.' in t.value or 'e' in t.value or 'E' in t.value:
        t.value = float(t.value)
    else:
        t.value = int(t.value)
    return t

t_ignore: str = ' \t\n\r'

def t_error(t: lex.LexToken) -> None:
    raise SyntaxError(f'Illegal character {t.value[0]} at position {t.lexpos}')

# Define ValueNode class for leaf values
class ValueNode:
    def __init__(
        self,
        type: Optional[str] = None,
        value: Any = None,
        nullable: bool = False,
        key: Optional[str] = None
    ) -> None:
        self.type: Optional[str] = type
        self.value: Any = value  # Actual value for comparison
        self.nullable: bool = nullable
        self.key: Optional[str] = key  # Attribute name



    def merge(self, other: Union['ValueNode', 'TypeNode', 'ListNode']) -> Union['ValueNode', 'TypeNode', 'ListNode']:
        if self.type is None:
            other.nullable = True
            return other
        # Only check for 'otype' and 'snippet'
        if self.key == "otype" or self.key == "snippet":
            if self.value is not None and other.value is not None:
                if self.value != other.value:
                    raise TypeError(f"Value mismatch for attribute '{self.key}': '{self.value}' vs '{other.value}'")
        # Handle type mismatches
        if self.type is None or other.type is None:
            self.nullable = True
        elif self.type != other.type:
            raise TypeError(f"Type mismatch for attribute '{self.key}': '{self.type}' vs '{other.type}'")
        return self

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {'type': self.type}
        if self.nullable:
            result['nullable'] = True
        return result

# Define TypeNode class to represent object types
class TypeNode:
    def __init__(
        self,
        type: str = 'object',
        attributes: Optional[Dict[str, Union['TypeNode', ValueNode, 'ListNode']]] = None,
        nullable: bool = False,
        otype: Optional[str] = None,
        snippet: bool = False,
        ref: Optional[str] = None
    ) -> None:
        self.type: str = type
        self.attributes: Dict[str, Union['TypeNode', ValueNode, 'ListNode']] = attributes if attributes else {}
        self.nullable: bool = nullable
        self.otype: Optional[str] = otype  # 'otype' value
        self.snippet: bool = snippet  # 'snippet' value (default to False)
        self.ref: Optional[str] = ref  # Reference to another type (otype)

    def merge(self, other: 'TypeNode') -> Union['TypeNode', None]:
        self.nullable = self.nullable or other.nullable
        if other.type is None:
            return self
        if self.type != other.type:
            raise TypeError(f"Type mismatch for otype '{self.otype}': '{self.type}' vs '{other.type}'")

        # Ensure 'otype' and 'snippet' match
        if self.otype != other.otype or self.snippet != other.snippet:
            print(f"Warning! Merging types with different 'otype' or 'snippet': '{self.otype}', '{self.snippet}' vs '{other.otype}', '{other.snippet}'")

        for key, attr in self.attributes.items():
            if key not in other.attributes.keys():
                attr.nullable = True
        # Merge attributes
        for key, attr in other.attributes.items():
            if key in self.attributes.keys():
                self.attributes[key] = self.attributes[key].merge(attr)
            else:
                attr.nullable = True
                self.attributes[key] = attr
        return self

    def to_dict(self, type_registry: 'TypeRegistry') -> Dict[str, Any]:
        result: Dict[str, Any] = {
            'type': self.type,
            'otype': self.otype,
            'snippet': self.snippet
        }
        if self.nullable:
            result['nullable'] = True
        if self.attributes:
            result['attributes'] = {}
            for key, attr in self.attributes.items():
                if isinstance(attr, TypeNode):
                    # It's a nested object; use 'ref'
                    result['attributes'][key] = {'ref': type_registry.get_ref(attr.otype)}
                    if attr.nullable:
                        result['attributes'][key]['nullable'] = True
                elif isinstance(attr, ListNode):
                    # It's a list; include its dictionary representation
                    result['attributes'][key] = attr.to_dict(type_registry)
                else:
                    # It's a ValueNode
                    result['attributes'][key] = attr.to_dict()
        return result

# Define ListNode class for array attributes
class ListNode:
    def __init__(self, element_type: Optional[Union[TypeNode, ValueNode, 'ListNode']] = None, nullable: bool = False) -> None:
        self.element_type: Optional[Union[TypeNode, ValueNode, 'ListNode']] = element_type
        self.nullable: bool = nullable

    def merge(self, other: Union[TypeNode, ValueNode, 'ListNode']) -> Union[TypeNode, ValueNode, 'ListNode']:
        self.nullable = self.nullable or other.nullable
        if self.element_type is not ListNode:
            return self
        if self.element_type is None:
            self.element_type = other.element_type
        elif other.element_type is not None:
            self.element_type = self.element_type.merge(other.element_type)
        return self

    def to_dict(self, type_registry: 'TypeRegistry') -> Dict[str, Any]:
        result: Dict[str, Any] = {
            'type': 'array'
        }
        if self.nullable:
            result['nullable'] = True
        if isinstance(self.element_type, TypeNode):
            # Reference to another type
            result['element'] = {'ref': type_registry.get_ref(self.element_type.otype)}
        elif isinstance(self.element_type, ListNode):
            # Nested array
            result['element'] = self.element_type.to_dict(type_registry)
        else:
            # ValueNode
            result['element'] = self.element_type.to_dict()
        return result

# Type registry to store type definitions by ('otype', 'snippet')
class TypeRegistry:
    def __init__(self) -> None:
        self.types: Dict[Tuple[str, bool], TypeNode] = {}  # Key: (otype, snippet), Value: TypeNode
        self.type_names: Dict[Tuple[str, bool], str] = {}  # Key: (otype, snippet), Value: Unique type name

    def register_type(self, otype: str, snippet: bool, type_node: TypeNode) -> None:
        snippet_append: str = ""
        if snippet:
            snippet_append = "_snippet"
        key: Tuple[str, bool] = (otype, snippet)
        if key in self.types:
            self.types[key].merge(type_node)
        else:
            self.types[key] = type_node
            self.type_names[key] = f"{otype}{snippet_append}"

    def get_type(self, otype: str, snippet: bool) -> Optional[TypeNode]:
        return self.types.get((otype, snippet), None)

    def get_type_name(self, key: Tuple[str, bool]) -> Optional[str]:
        return self.type_names.get(key, None)

    def get_preferred_snippet(self, otype: str) -> Optional[bool]:
        # Prefer 'snippet' value False, else True
        for snippet in [False, True]:
            key = (otype, snippet)
            if key in self.types:
                return snippet
        return None

    def get_ref(self, otype: str) -> Optional[str]:
        # Return the type name with snippet=False if exists, else snippet=True
        snippet = self.get_preferred_snippet(otype)
        if snippet is not None:
            key = (otype, snippet)
            return self.type_names.get(key, None)
        return None

    def to_dict(self) -> Dict[str, Any]:
        output: Dict[str, Any] = {}
        for key, type_node in self.types.items():
            type_name = self.type_names[key]
            output[type_name] = type_node.to_dict(self)
        return output

# Initialize global type registry
type_registry: TypeRegistry = TypeRegistry()

# Parsing rules
def p_json(p: yacc.YaccProduction) -> None:
    'json : value'
    p[0] = p[1]

def p_value_object(p: yacc.YaccProduction) -> None:
    'value : object'
    p[0] = p[1]

def p_value_array(p: yacc.YaccProduction) -> None:
    'value : array'
    p[0] = p[1]

def p_array(p: yacc.YaccProduction) -> None:
    'array : LBRACKET elements RBRACKET'
    elements: List[Any] = p[2]
    if not elements:
        # Empty array, element_type unknown, set to None or any
        p[0] = ListNode(element_type=None, nullable=False)
    else:
        # Assume all elements have the same type
        first_element = elements[0]
        for elem in elements[1:]:
            if type(elem) != type(first_element):
                raise TypeError("All elements in array must be of the same type")
            if hasattr(first_element, 'type') and hasattr(elem, 'type'):
                if first_element.type != elem.type:
                    raise TypeError("All object elements in array must have the same type")
        # Create ListNode with element_type
        list_node = ListNode(element_type=first_element, nullable=False)
        p[0] = list_node

def p_elements_single(p: yacc.YaccProduction) -> None:
    'elements : value'
    p[0] = [p[1]]

def p_elements_multiple(p: yacc.YaccProduction) -> None:
    'elements : value COMMA elements'
    p[0] = [p[1]] + p[3]

def p_value_string(p: yacc.YaccProduction) -> None:
    'value : STRING'
    # Check if the string is a date
    date_pattern: str = r'\d{4}-\d{2}-\d{2}'
    if re.fullmatch(date_pattern, p[1]):
        p[0] = ValueNode(type='date', value=p[1])
    else:
        p[0] = ValueNode(type='string', value=p[1])

def p_value_number(p: yacc.YaccProduction) -> None:
    'value : NUMBER'
    if isinstance(p[1], int):
        p[0] = ValueNode(type='int', value=p[1])
    else:
        p[0] = ValueNode(type='float', value=p[1])

def p_value_true(p: yacc.YaccProduction) -> None:
    'value : TRUE'
    p[0] = ValueNode(type='bool', value=p[1])

def p_value_false(p: yacc.YaccProduction) -> None:
    'value : FALSE'
    p[0] = ValueNode(type='bool', value=p[1])

def p_value_null(p: yacc.YaccProduction) -> None:
    'value : NULL'
    p[0] = ValueNode(nullable=True)

def p_object(p: yacc.YaccProduction) -> None:
    'object : LBRACE members RBRACE'
    attributes: Dict[str, Union[TypeNode, ValueNode, ListNode]] = p[2]

    # Extract 'otype' and 'snippet'
    otype_node: Optional[ValueNode] = attributes.get('otype', None)
    if otype_node:
        otype: Optional[str] = otype_node.value
    else:
        otype = None

    snippet_node: Optional[ValueNode] = attributes.get('snippet', None)
    if snippet_node:
        if snippet_node.value is True:
            snippet: bool = True
        elif snippet_node.value is False:
            snippet = False
        else:
            raise TypeError(f"Invalid 'snippet' value: '{snippet_node.value}'")
    else:
        snippet = False  # Default to False if not present

    # Create TypeNode
    type_node = TypeNode(
        type='object',
        attributes=attributes,
        nullable=False,
        otype=otype,
        snippet=snippet
    )

    # Register type
    if otype is not None:
        type_registry.register_type(otype, snippet, type_node)

    p[0] = type_node

def p_members_single(p: yacc.YaccProduction) -> None:
    'members : member'
    p[0] = p[1]

def p_members_multiple(p: yacc.YaccProduction) -> None:
    'members : member COMMA members'
    p[0] = p[3]
    for key, value in p[1].items():
        if key in p[0]:
            try:
                p[0][key] = p[0][key].merge(value)
            except TypeError as e:
                raise TypeError(f"At attribute '{key}': {e}")
        else:
            p[0][key] = value

def p_member(p: yacc.YaccProduction) -> None:
    'member : STRING COLON value'
    key: str = p[1]
    value: Union[TypeNode, ValueNode, ListNode] = p[3]
    if isinstance(value, TypeNode):
        # It's a nested object with 'otype'
        ref_type_name: Optional[str] = type_registry.get_ref(value.otype)
        if ref_type_name:
            # Set reference
            value.ref = ref_type_name
            value.attributes = {}  # Clear attributes to avoid duplication
        else:
            # Register the new type with its snippet value
            type_registry.register_type(value.otype, value.snippet, value)
            ref_type_name = type_registry.get_ref(value.otype)
            value.ref = ref_type_name
            value.attributes = {}
    elif isinstance(value, ListNode):
        # It's a list; ensure element type is registered if necessary
        if isinstance(value.element_type, TypeNode):
            ref_type_name = type_registry.get_ref(value.element_type.otype)
            if ref_type_name:
                value.element_type.ref = ref_type_name
                # value.element_type.attributes = {}  # Clear attributes to avoid duplication
            else:
                # Register the new type
                type_registry.register_type(value.element_type.otype, value.element_type.snippet, value.element_type)
                ref_type_name = type_registry.get_ref(value.element_type.otype)
                value.element_type.ref = ref_type_name
                value.element_type.attributes = {}
    # Assign the value to the key
    p[0] = {key: value}

def p_error(p: Optional[lex.LexToken]) -> None:
    if p:
        raise SyntaxError(f'Syntax error at "{p.value}"')
    else:
        raise SyntaxError("Syntax error at EOF")

# Build lexer and parser
lexer: lex.LexToken = lex.lex()
parser: yacc.LRParser = yacc.yacc()

# Example usage
def main() -> None:
    data_list: List[str] = [
        '''
        [
            {
                "otype": "person",
                "snippet": true,
                "name": "Alice",
                "age": 30,
                "hobbies": ["reading", "cycling", "hiking"]
            },
            {
                "otype": "person",
                "snippet": false,
                "name": "Bob",
                "age": 25,
                "email": "bob@example.com",
                "languages": [
                    {
                        "otype": "language",
                        "snippet": false,
                        "name": "Hungarian"
                    },
                    {
                        "otype": "language",
                        "snippet": false,
                        "name": "English",
                        "dialect": "British"
                    }
                ],
                "hobbies": ["gaming", "painting"]
            },
            {
                "otype": "person",
                "snippet": true,
                "name": "Charlie",
                "age": 35,
                "email": null,
                "hobbies": ["swimming", "photography"]
            }
        ]
        ''',
        '''
        [
            {
                "otype" : "language",
                "snippet" : false,
                "name" : "Hungarian"
            },
            {
                "otype" : "language",
                "snippet" : true,
                "name" : "English",
                "dialect": "British"
            }
        ]
        '''
    ]

    try:
        for data in data_list:
            # Parse the JSON data
            result = parser.parse(data)
            # Since data can be an array or object, handle both
            if isinstance(result, list):
                for item in result:
                    pass  # Parsing and registration handled during parsing
            else:
                pass  # Parsing and registration handled during parsing

        # After parsing all data, output the type definitions
        types_output: Dict[str, Any] = type_registry.to_dict()
        print(json.dumps(types_output, indent=2))
    except TypeError as e:
        print(f'Type error: {e}')
    except SyntaxError as e:
        print(f'Syntax error: {e}')

if __name__ == '__main__':
    main()
