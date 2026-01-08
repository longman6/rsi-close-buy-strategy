import csv
import os

input_file = 'data_1903_20260103.csv'
output_file = 'kospi200_list.txt'

def parse_csv():
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return

    output_lines = []
    
    try:
        # Try cp949 (most common for Korean Windows CSVs)
        with open(input_file, 'r', encoding='cp949') as f:
            reader = csv.reader(f)
            # Skip header? Header row seems to be present based on previous `head` output.
            # "ڵ,,..." -> "종목코드,종목명,..."
            next(reader, None) 
            
            count = 0
            for row in reader:
                if len(row) < 2: continue
                
                code = row[0].strip()
                name = row[1].strip()
                
                # Format: {'code': '005930', 'name': '삼성전자'}
                line = f"{{'code': '{code}', 'name': '{name}'}}"
                output_lines.append(line)
                count += 1
                
        print(f"Successfully parsed {count} items.")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(",\n".join(output_lines))
            # analyze logic handles optional trailing comma, but let's stick to simple join.
            # actually user's kosdaq list had formatting with newlines.
            
        print(f"Saved to {output_file}")
        
    except UnicodeDecodeError:
        print("Encoding Error: Failed to decode with cp949")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    parse_csv()
