//定义TS类型
export type Role = 'user' | 'assistant' ;
export interface Message {
    id: number;
    role: Role;
    content: string;
    createdAt?: string;
}

export interface ChatRequest {
    message: string;
}

export interface ChatResponse {
    answer: string;
}
