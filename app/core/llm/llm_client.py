from http import HTTPStatus
import os
import random
import time

from dashscope import Generation
import openai
from openai import OpenAI, OpenAIError
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


class LlmClient:
    def __init__(self, model="", model_path="", platform=""):
        self.model = model
        self.model_path = model_path
        self.current_device = None
        self.tokenizer = None

        platform_form_env = os.getenv("LLM_PLATFORM")
        if platform != "":
            self.platform = platform
        elif platform_form_env is not None:
            self.platform = platform_form_env
        else:
            self.platform = "dashscope"
        if model_path != "":
            # check current device
            self.current_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            # load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
            # load model
            self.model = AutoModelForCausalLM.from_pretrained(
                model_path, torch_dtype=torch.float16
            ).to(self.current_device)

    def call_with_messages(self, messages):
        if self.model_path == "":
            output = self.call_with_messages_online(messages)
        else:
            output = self.call_with_messages_local(messages)
        return output

    def call_with_messages_online(self, messages):
        if self.platform == "openai":
            return self.call_with_messages_online_for_openai(messages)
        elif self.platform == "dashscope":
            return self.call_with_messages_online_for_dashscope(messages)
        else:
            print(f"Unsupposed platform:{self.platform}")
            return ""

    def call_with_messages_local(self, messages):
        # generate content
        inputs = self.tokenizer.apply_chat_template(
            messages, tokenize=True, return_dict=True, return_tensors="pt"
        ).to(self.current_device)

        # add more args
        output = self.model.generate(
            **inputs,
            do_sample=True,
            temperature=0.8,
            top_p=0.8,
            top_k=50,
            pad_token_id=self.tokenizer.eos_token_id,
            eos_token_id=self.tokenizer.eos_token_id,
            max_new_tokens=2048,
        )

        # deal with output and return
        output = self.tokenizer.decode(
            output[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True
        )

        return output

    def call_with_messages_online_for_openai(self, messages):
        try:
            openai_client = OpenAI(
                api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL")
            )
            response = openai_client.chat.completions.create(
                model=self.model, messages=messages, temperature=0
            )
            return response.choices[0].message.content
        except openai.RateLimitError:
            print("there are too many request,ready to retry in 1 second")
            time.sleep(1)
            print("begin to retry")
            return self.call_with_messages_online_for_openai(messages)
        except OpenAIError:
            print("Failed!", messages[1]["content"])

    def call_with_messages_online_for_dashscope(self, messages):
        response = Generation.call(
            model=self.model,
            messages=messages,
            seed=random.randint(1, 10000),
            temperature=0.8,
            top_p=0.8,
            top_k=50,
            result_format="message",
        )
        if response.status_code == HTTPStatus.OK:
            content = response.output.choices[0].message.content
            return content
        else:
            if response.code == 429:  # Requests rate limit exceeded
                print(
                    f"Request id: {response.request_id}, Status code: {response.status_code}"
                    + f", error code: {response.code}, error message: {response.message}"
                    + "too many request,ready to retry in 1 second "
                )
                time.sleep(1)
                print(f"Request id: {response.request_id}, begin to retry")
                return self.call_with_messages_online_for_dashscope(messages)
            else:
                print(
                    f"Request id: {response.request_id}, Status code: {response.status_code}"
                    + f", error code: {response.code}, error message: {response.message}"
                )
                print("Failed!", messages[1]["content"])
                return ""


if __name__ == "__main__":
    llm_client = LlmClient(model="qwen-plus-0723")
    messages = [
        {
            "role": "system",
            "content": "",
        },
        {"role": "user", "content": ""},
    ]
    print(llm_client.call_with_messages(messages))
