"""Provider client with safe failure messages and actual token accounting."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import httpx

from app.config import llm_settings

TOKEN_FIELDS = ('input_tokens', 'output_tokens', 'reasoning_tokens', 'total_tokens')
_last_request: dict = {}


class LLMError(RuntimeError):
    def __init__(self, code: str, message: str, usage: dict | None = None):
        super().__init__(message)
        self.code = code
        self.usage = usage or {}


def available() -> bool:
    return bool(llm_settings()[1])


def _fingerprint() -> str:
    return hashlib.sha256(repr(llm_settings()).encode()).hexdigest()


def status() -> dict:
    configured = available()
    current = _last_request if _last_request.get('fingerprint') == _fingerprint() else {}
    return {'configured': configured, 'model': llm_settings()[2],
            'mode': current.get('mode', 'configured' if configured else 'fallback'),
            'message': current.get('message', 'Ключ задан; успешный ответ ещё не получен.' if configured else 'API-ключ не задан.'),
            'checked_at': current.get('checked_at')}


def metadata() -> dict:
    return {'mode': 'fallback', 'model': llm_settings()[2], 'calls': 0,
            **{field: 0 for field in TOKEN_FIELDS}}


def add_usage(target: dict, message: dict) -> None:
    usage = message.get('_usage', {})
    target['calls'] += 1
    for field in TOKEN_FIELDS:
        target[field] += usage.get(field, 0) or 0


def _usage(data: dict) -> dict:
    usage = data.get('usage') or {}
    incoming = usage.get('input_tokens', usage.get('prompt_tokens', 0)) or 0
    outgoing = usage.get('output_tokens', usage.get('completion_tokens', 0)) or 0
    details = usage.get('output_tokens_details', usage.get('completion_tokens_details')) or {}
    return {'input_tokens': incoming, 'output_tokens': outgoing,
            'reasoning_tokens': details.get('reasoning_tokens', 0) or 0,
            'total_tokens': usage.get('total_tokens', incoming + outgoing) or 0}


def _post(path: str, body: dict) -> dict:
    global _last_request
    base, key, _ = llm_settings()
    fingerprint = _fingerprint()
    try:
        response = httpx.post(f'{base}/{path}', headers={'Authorization': f'Bearer {key}'},
                              json=body, timeout=90)
        data = response.json()
        if not response.is_success:
            code = (data.get('error') or {}).get('code')
            if response.status_code == 401:
                raise LLMError('invalid_key', 'API-ключ отклонён или отозван. Обновите ключ в локальном .env.')
            if code == 'insufficient_quota':
                raise LLMError('quota', 'У API-аккаунта закончился доступный баланс или квота.')
            if response.status_code == 429:
                raise LLMError('rate_limit', 'Достигнут лимит запросов API. Повторите позже.')
            if response.status_code == 404 or code == 'model_not_found':
                raise LLMError('model_unavailable', 'Выбранная модель недоступна этому API-аккаунту.')
            raise LLMError('provider_error', f'Провайдер отклонил запрос (HTTP {response.status_code}).')
        if data.get('status') == 'incomplete':
            raise LLMError('incomplete', 'Модель не завершила ответ.', _usage(data))
    except (httpx.HTTPError, ValueError) as error:
        error = LLMError('connection', 'Не удалось получить ответ от API. Проверьте соединение и адрес провайдера.')
        _last_request = {'fingerprint': fingerprint, 'mode': 'fallback', 'message': str(error),
                         'checked_at': datetime.now(timezone.utc).isoformat()}
        raise error
    except LLMError as error:
        _last_request = {'fingerprint': fingerprint, 'mode': 'fallback', 'message': str(error),
                         'checked_at': datetime.now(timezone.utc).isoformat()}
        raise
    _last_request = {'fingerprint': fingerprint, 'mode': 'live', 'message': 'API вернул ответ.',
                     'checked_at': datetime.now(timezone.utc).isoformat()}
    return data


def chat(messages: list[dict], *, tools: list[dict] | None = None) -> dict:
    _, key, model = llm_settings()
    if not key:
        raise LLMError('no_key', 'API-ключ не задан. Используется расчётный отчёт.')
    if model.startswith('gpt-6-'):
        previous_index = next((i for i in range(len(messages) - 1, -1, -1)
                               if messages[i].get('_response_id')), None)
        recent = messages[previous_index + 1:] if previous_index is not None else messages
        inputs = [{'type': 'function_call_output', 'call_id': item['tool_call_id'], 'output': item['content']}
                  if item['role'] == 'tool' else {'role': item['role'], 'content': item['content']}
                  for item in recent if item['role'] != 'system']
        body = {'model': model, 'instructions': '\n'.join(item['content'] for item in messages if item['role'] == 'system'),
                'input': inputs, 'reasoning': {'effort': 'medium'}}
        if previous_index is not None:
            body['previous_response_id'] = messages[previous_index]['_response_id']
        if tools:
            body['tools'] = [{'type': 'function', **tool['function'], 'strict': False} for tool in tools]
        data = _post('responses', body)
        output = data.get('output', [])
        return {'role': 'assistant', 'content': ''.join(part['text'] for item in output if item['type'] == 'message'
                for part in item.get('content', []) if part['type'] == 'output_text'),
                'tool_calls': [{'id': item['call_id'], 'type': 'function', 'function': {
                    'name': item['name'], 'arguments': item['arguments']}} for item in output if item['type'] == 'function_call'],
                '_response_id': data['id'], '_usage': _usage(data)}
    body = {'model': model, 'messages': [{k: v for k, v in item.items() if not k.startswith('_')} for item in messages]}
    if tools:
        body['tools'] = tools
    data = _post('chat/completions', body)
    return {**data['choices'][0]['message'], '_usage': _usage(data)}
