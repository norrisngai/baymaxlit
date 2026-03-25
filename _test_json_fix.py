import re, json

def safe_json_loads(raw):
    """Parse JSON, fixing LaTeX backslash escapes on failure."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        fixed = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)
        return json.loads(fixed)

# Test 1: LaTeX math with unescaped backslashes
raw1 = r'[{"q":"If \(x+3=7\), find \(x\)"}]'
r1 = safe_json_loads(raw1)
print(f"Test 1 (LaTeX): {r1[0]['q']}")

# Test 2: Normal JSON with proper escapes should still work
raw2 = '{"msg": "hello\\nworld", "path": "C:\\\\Users"}'
r2 = safe_json_loads(raw2)
print(f"Test 2 (normal escapes): {r2}")

# Test 3: Unicode escapes should still work  
raw3 = '{"text": "\\u4e2d\\u6587"}'
r3 = safe_json_loads(raw3)
print(f"Test 3 (unicode): {r3}")

# Test 4: Display math \[...\]
raw4 = r'[{"q":"Solve: \[x^2 - 4 = 0\]"}]'
r4 = safe_json_loads(raw4)
print(f"Test 4 (display math): {r4[0]['q']}")

# Test 5: Mixed \angle etc
raw5 = r'[{"q":"If \(\angle ABC = 110°\), find \(\angle ADC\)."}]'
r5 = safe_json_loads(raw5)
print(f"Test 5 (angle): {r5[0]['q']}")

# Test 6: Properly escaped LaTeX (Gemini did it right)
raw6 = '[{"q":"If \\\\(x+3=7\\\\), find \\\\(x\\\\)"}]'
r6 = safe_json_loads(raw6)
print(f"Test 6 (pre-escaped): {r6[0]['q']}")

print("\nAll tests passed!")
