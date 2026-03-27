import os

migradas_path = r'C:\Users\benja\Desktop\mati\app\vehiculos\rutas_migradas.py'
routes_path = r'C:\Users\benja\Desktop\mati\app\vehiculos\routes.py'

# Read routes.py
with open(routes_path, 'r', encoding='utf-8') as f:
    routes_content = f.read()

# Verify if register_vehiculos_control expects we close its return bp
if routes_content.strip().endswith('return bp'):
    routes_content = routes_content.rsplit('return bp', 1)[0]
else:
    print("Warning: return bp not found at end of routes.py")

# Read migradas and indent by 4 spaces
with open(migradas_path, 'r', encoding='utf-8') as f:
    migradas_lines = f.readlines()

indented_migradas = ""
for line in migradas_lines:
    if line.strip() == "":
        indented_migradas += "\n"
    else:
        indented_migradas += "    " + line

# Combine them
final_content = routes_content + "\n" + indented_migradas + "\n    return bp\n"

with open(routes_path, 'w', encoding='utf-8') as f:
    f.write(final_content)

print("Merged successfully!")
