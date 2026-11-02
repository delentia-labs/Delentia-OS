"""
A web page for the scripted demos of Delentia (a Hugging Face Space, or `python app.py` on your own computer).

All the logic is in runner.py. This file only builds the page: three buttons, a language switch and a place for the report. It asks for no sign-in and no key, and accepts no text from the visitor.
"""
import gradio as gr

import runner

HEADER = """# Delentia: try the safety demo in your browser

Delentia is an experimental, self-hosted agent runtime: risky actions wait for a person's signature, text from outside cannot steer the agent, and every step goes into a signed log.
**Nothing here needs a model, a key or an account.** Press a button; the demo runs on this server in a fresh folder and shows the report. (Source and install: [github.com/delentia-labs/Delentia-OS](https://github.com/delentia-labs/Delentia-OS)
· `pip install delentia-os` · [what is measured and what is not](https://github.com/delentia-labs/Delentia-OS/blob/main/docs/release/RELEASE_LEVELS.md).)
"""


def go(scenario: str, lang: str) -> str:
    try:
        return runner.run_scenario(scenario, lang)
    except runner.DemoError as exc:
        return f"**The demo could not run:** {exc}. Nothing was changed. You can try again, or install Delentia and run `delentia demo run compare --scripted` yourself."


with gr.Blocks(title="Delentia scripted demo") as demo:
    gr.Markdown(HEADER)
    notice = gr.Markdown(runner.intro("en"))
    lang = gr.Radio(choices=[("English", "en"), ("ไทย", "th")], value="en", label="Language of the demo files and the report")
    lang.change(lambda value: runner.intro(value), lang, notice)
    with gr.Row():
        buttons = {key: gr.Button(label) for key, label in runner.LABELS.items()}
    report = gr.Markdown("_Press a button. A run takes a few seconds._")
    def handler_for(scenario: str):
        def handler(language: str) -> str:
            return go(scenario, language)
        return handler

    for key, button in buttons.items():
        button.click(handler_for(key), lang, report, concurrency_limit=2)

if __name__ == "__main__":
    demo.queue(max_size=8).launch()
