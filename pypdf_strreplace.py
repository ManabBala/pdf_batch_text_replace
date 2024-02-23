#!/usr/bin/env python3
import argparse
import sys
import io
import binascii
import pypdf
from typing import Any, Callable, Dict, Tuple, Union, cast
from pypdf.generic import DictionaryObject, NameObject, RectangleObject, ContentStream
from pypdf.generic._base import TextStringObject, ByteStringObject, NumberObject, FloatObject
from pypdf.constants import PageAttributes as PG
from pypdf._cmap import build_char_map
import pprint

class CharMap:
    def __init__(self, subtype, halfspace, encoding, map, ft):
        [setattr(self, k, v) for k,v in locals().items()]
    @classmethod
    def from_char_map(cls, subtype:str, halfspace:float, encoding:Union[str, Dict[int, str]], map:Dict[str, str], ft:DictionaryObject):
        return cls(subtype, halfspace, encoding, map, ft)
    def decode(self, text:Union[TextStringObject,ByteStringObject]):
        #print("Decoding", text.get_original_bytes(), "with this map:")
        #pprint.pprint(self.map)
        if (isinstance(text, TextStringObject) and self.encoding == "charmap"):
            # decoding with ascii is a wild guess
            return "".join(text.get_original_bytes().decode('ascii').translate(str.maketrans(self.map)))
        elif (isinstance(text, ByteStringObject)):
            return "".join(text.decode(self.encoding).translate(str.maketrans(self.map)))
        elif (isinstance(self.encoding, dict)):
            return str(text)
        else:
            raise NotImplementedError(f"Cannot decode „{text}“ with this {type(self.encoding)} encoding: {self.encoding}")

# from https://github.com/py-pdf/pypdf/blob/27d0e99/pypdf/_page.py#L1546
def get_char_maps(obj: Any, space_width: float = 200.0):
    cmaps = {}
    objr = obj
    while NameObject(PG.RESOURCES) not in objr:
        # /Resources can be inherited sometimes so we look to parents
        objr = objr["/Parent"].get_object()
    resources_dict = cast(DictionaryObject, objr[PG.RESOURCES])
    if "/Font" in resources_dict:
        for font_id in cast(DictionaryObject, resources_dict["/Font"]):
            cmaps[font_id] = CharMap.from_char_map(*build_char_map(font_id, space_width, obj))
    return cmaps

class Context:
    def __init__(self, font:str = None):
        self.font = font
    def clone(self):
        return type(self)(self.font)
class PDFOperation:
    def __init__(self, operands, operator, context:Context):
        self.operands = operands
        self.operator = operator
        self.context = context
    @classmethod
    def from_tuple(cls, operands, operator, context:Context):
        operator = operator.decode('ascii') # PDF operators are indeed ascii encoded
        classname = f"PDFOperation{operator}"
        if (classname in globals()):
            return globals()[classname](operands, context)
        return cls(operands, operator, None)
    def __repr__(self):
        return self.operator
    def write_to_stream(self, stream):
        #print(self.operands)
        for op in self.operands:
            op.write_to_stream(stream)
            stream.write(b" ")
        stream.write(self.operator.encode("ascii")) # PDF operators are indeed ascii encoded
        stream.write(b"\n")
    def get_text_map(self, charmaps):
        return []
class PDFOperationTd(PDFOperation):
    def __init__(self, operands, context:Context):
        super().__init__(operands, "Td", None)
    def __repr__(self):
        return f"{self.operands} {self.operator}"
    def get_text_map(self, charmaps):
        map = []
        tx, ty = self.operands
        if (ty != 0):
            # consider a vertical adjustment starting a new line
            map.append((None, "\n"))
        if (tx != 0):
            # display horizontal adjustment as space. total guess. works for the xelatex sample.
            map.append((None, " "))
        return map
class PDFOperationTf(PDFOperation):
    def __init__(self, operands, context:Context):
        super().__init__(operands, "Tf", None)
        context.font = operands[0]
class PDFOperationTJ(PDFOperation):
    def __init__(self, operands:list[list[Union[TextStringObject,ByteStringObject,NumberObject]]], context:Context):
        if (len(operands) != 1):
            raise ValueError(f"PDFOperationTJ expects one non-empty Array of Array")
        super().__init__(operands, "TJ", context.clone())
    def __repr__(self):
        return f"„{self.operands[0]}“ {self.operator}"
    def get_text_map(self, charmaps):
        map = []
        for operand in self.operands[0]:
            if (isinstance(operand, NumberObject) or isinstance(operand, FloatObject)):
                if (operand < -charmaps[self.context.font].halfspace):
                    # display big horizontal adjustment as space. total guess. works for the xelatex sample.
                    map.append((operand, " "))
            else:
                map.append((operand, charmaps[self.context.font].decode(operand)))
        return map
class PDFOperationTj(PDFOperation):
    def __init__(self, operands:list[Union[TextStringObject,ByteStringObject]], context:Context):
        if (len(operands) != 1):
            raise ValueError(f"PDFOperationTj expects one non-empty Array of TextStringObject")
        super().__init__(operands, "Tj", context.clone())
    def __repr__(self):
        return f"„{self.operands[0]}“ {self.operator}"
    def get_text_map(self, charmaps):
        return [(self.operands[0], charmaps[self.context.font].decode(self.operands[0]))]

def analyze_content(content:ContentStream, charmaps):
    #print(content.get_data())
    #pprint.pprint(content.operations)
    context = Context()
    operations = [PDFOperation.from_tuple(ops, op, context) for ops, op in content.operations]
    #pprint.pprint(operations)
    text_maps = [op.get_text_map(charmaps) for op in operations]
    text_maps = [tm for tm in text_maps if tm]
    print("".join(["".join([t[1] for t in text_map]) for text_map in text_maps]))
    #pprint.pprint(texts)
    # stream = io.BytesIO()
    # [op.write_to_stream(stream) for op in operations]
    # print(stream.getvalue())
    #content.set_data(stream.getvalue())

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Replace text in a PDF file.')
    parser.add_argument('--input', type=str, required=True)
    parser.add_argument('--output', type=str)
    parser.add_argument('--papersize', type=str, default="A4")
    args = parser.parse_args()
    total_replacements = 0
    reader = pypdf.PdfReader(args.input)
    writer = pypdf.PdfWriter()

    for page_index, page in enumerate(reader.pages):
        #print(f"Processing page {page_index+1}…")

        charmaps = get_char_maps(page)
            
        contents = page.get_contents()
        # NOTE: contents may be None, ContentStream, EncodedStreamObject, ArrayObject
        if (isinstance(contents, pypdf.generic._data_structures.ArrayObject)):
            for content in contents:
                analyze_content(content, charmaps)
        elif (isinstance(contents, pypdf.generic._data_structures.ContentStream)):
            analyze_content(contents, charmaps)
        else:
            raise NotImplementedError(f"Cannot modify {type(contents)}.")
        page.replace_contents(contents)

        papersize = getattr(pypdf.PaperSize, args.papersize)
        # TODO: find out how to preserve original mediabox
        page.mediabox = RectangleObject((0, 0, papersize.width, papersize.height))
        writer.add_page(page)

    if (args.output):
        writer.write(args.output)
