"""Debug page 17 extraction."""
import fitz
from collections import Counter
import re

doc = fitz.open('data/bank-documents/ZAVA_a-guide-to-fees-and-charges-for-personal-accounts.pdf')
page = doc[16]  # Page 17
page_height = page.rect.height
page_dict = page.get_text('dict')

# Replicate extract_main_text logic
font_sizes = []
for block in page_dict.get('blocks', []):
    if block.get('type') != 0:
        continue
    for line in block.get('lines', []):
        for span in line.get('spans', []):
            if span.get('text', '').strip():
                font_sizes.append(span.get('size', 12))

if not font_sizes:
    print('No font sizes found - that is the bug!')
else:
    body_font_size = Counter(font_sizes).most_common(1)[0][0]
    footnote_size_threshold = body_font_size * 0.8
    footnote_y_threshold = page_height * 0.80
    
    print(f'body_font_size: {body_font_size}')
    print(f'footnote_size_threshold: {footnote_size_threshold}')
    print(f'footnote_y_threshold: {footnote_y_threshold}')
    
    text_parts = []
    for block in page_dict.get('blocks', []):
        if block.get('type') != 0:
            continue
        
        block_lines = []
        for line in block.get('lines', []):
            line_parts = []
            include_line = True
            
            for span in line.get('spans', []):
                span_text = span.get('text', '')
                span_size = span.get('size', 12)
                span_y = span.get('origin', [0, 0])[1]
                
                print(f'Span: text="{span_text}" size={span_size} y={span_y}')
                print(f'  Check: y ({span_y}) > threshold ({footnote_y_threshold})? {span_y > footnote_y_threshold}')
                print(f'  Check: size ({span_size}) < threshold ({footnote_size_threshold})? {span_size < footnote_size_threshold}')
                
                if span_y > footnote_y_threshold and span_size < footnote_size_threshold:
                    if re.match(r'^[\(\[]?\d+[\)\]]?\s|^[†‡§\*]\s', span_text.strip()):
                        include_line = False
                        break
                
                line_parts.append(span_text)
            
            print(f'  include_line: {include_line}, line_parts: {line_parts}')
            if include_line and line_parts:
                block_lines.append(''.join(line_parts))
        
        if block_lines:
            text_parts.append('\n'.join(block_lines))
    
    print(f'\nExtracted text: {text_parts}')
