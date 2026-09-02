import request from '@/utils/request';

export function chat(message: string) {
    return request.post('/api/chat', {
        message,
    });
}