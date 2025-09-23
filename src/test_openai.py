import os
from openai import OpenAI

def main():
    # Lee la API key desde la variable de entorno
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("❌ No se encontró la variable OPENAI_API_KEY")

    client = OpenAI(api_key=api_key)

    # Petición mínima de prueba
    resp = client.chat.completions.create(
        model="gpt-4o-mini",   # puedes usar "gpt-5" si quieres más heavy
        messages=[
            {"role": "system", "content": "Eres un asistente útil."},
            {"role": "user", "content": "Dame un resumen de 2 líneas de por qué Python es útil para ciencia de datos."}
        ]
    )

    print("✅ Respuesta de OpenAI:")
    print(resp.choices[0].message.content)

if __name__ == "__main__":
    main()
