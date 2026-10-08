from src.llm.medgemma_provider import MedGemmaProvider


def main():
    provider = MedGemmaProvider()

    health = provider.healthcheck()
    print("ESTADO MEDGEMMA:")
    print(health)

    if health.get("status") != "ready":
        return

    result = provider.chat(
        messages=[
            {
                "role": "user",
                "content": "Responde brevemente: ¿estás disponible?",
            }
        ],
        temperature=0.1,
        max_tokens=80,
    )

    print("\nRESPUESTA:")
    print(result)


if __name__ == "__main__":
    main()
