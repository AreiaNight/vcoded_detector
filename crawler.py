import requests
from pathlib import Path

#Compone y verifica el url para acceder al source code sin pasar por la main page
url = input("URL: ")
response = requests.get(url)
url = ("view-source:" + url)

if response.status_code == 200:
    print("Page is avalibe")

print(url)

html = response.text.lower()

#El Path debe tener adentro el path del archiv. Se lee con read_text y el encoding.
texto = Path("wordlist.txt").read_text(encoding="utf-8")
#.splitlines() corta el texto cada vez que encuentra un salto de línea y devuelve una lista.
lineas = texto.splitlines()
#print(lineas)


limpias = []
total = 0

for linea in lineas:
    cleaning = linea.strip()
    cleaningB = cleaning.lower()
    if cleaningB:
        limpias.append(cleaningB)

for senal in limpias:
    conteo = html.count(senal)
    if conteo > 0:
        print(senal, conteo)
    total = total + conteo

print("Total:", total)
