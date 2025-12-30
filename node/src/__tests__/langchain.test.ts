import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DiagnyxCallbackHandler } from '../callbacks/langchain';
import type { Diagnyx } from '../client';
import type { LLMCallData } from '../types';

// Mock Diagnyx client
const createMockDiagnyx = () => {
  return {
    trackCall: vi.fn(),
    config: {
      captureFullContent: false,
      contentMaxLength: 10000,
    },
  } as unknown as Diagnyx;
};

describe('DiagnyxCallbackHandler', () => {
  let mockDiagnyx: Diagnyx;
  let handler: DiagnyxCallbackHandler;

  beforeEach(() => {
    mockDiagnyx = createMockDiagnyx();
    handler = new DiagnyxCallbackHandler(mockDiagnyx, {
      projectId: 'test-project',
      environment: 'test',
      userIdentifier: 'test-user',
    });
  });

  describe('constructor', () => {
    it('should initialize with options', () => {
      expect(handler.name).toBe('DiagnyxCallbackHandler');
    });

    it('should initialize with default options', () => {
      const defaultHandler = new DiagnyxCallbackHandler(mockDiagnyx);
      expect(defaultHandler.name).toBe('DiagnyxCallbackHandler');
    });
  });

  describe('handleLLMStart', () => {
    it('should record start time and metadata', () => {
      const runId = 'test-run-id';

      handler.handleLLMStart(
        { name: 'ChatOpenAI', kwargs: { model: 'gpt-4' } },
        ['Hello, world!'],
        runId,
      );

      // Verify internal state (we can check this indirectly through handleLLMEnd)
      expect((mockDiagnyx.trackCall as any).mock.calls.length).toBe(0);
    });
  });

  describe('handleChatModelStart', () => {
    it('should record start time and convert messages to prompts', () => {
      const runId = 'test-run-id';
      const messages = [
        [
          { content: 'Hello', type: 'human' },
          { content: 'Hi there!', type: 'ai' },
        ],
      ];

      handler.handleChatModelStart(
        { name: 'ChatOpenAI', kwargs: { model: 'gpt-4' } },
        messages,
        runId,
      );

      expect((mockDiagnyx.trackCall as any).mock.calls.length).toBe(0);
    });
  });

  describe('handleLLMEnd', () => {
    it('should track successful LLM call', () => {
      const runId = 'test-run-id';

      // Start the call
      handler.handleLLMStart(
        { kwargs: { model: 'gpt-4' } },
        ['Hello'],
        runId,
      );

      // End the call
      const output = {
        llmOutput: {
          modelName: 'gpt-4',
          tokenUsage: {
            promptTokens: 10,
            completionTokens: 20,
          },
        },
        generations: [[{ text: 'Hi there!' }]],
      };

      handler.handleLLMEnd(output, runId);

      expect(mockDiagnyx.trackCall).toHaveBeenCalledTimes(1);
      const callData = (mockDiagnyx.trackCall as any).mock.calls[0][0] as LLMCallData;

      expect(callData.model).toBe('gpt-4');
      expect(callData.provider).toBe('openai');
      expect(callData.inputTokens).toBe(10);
      expect(callData.outputTokens).toBe(20);
      expect(callData.status).toBe('success');
      expect(callData.projectId).toBe('test-project');
      expect(callData.environment).toBe('test');
      expect(callData.userIdentifier).toBe('test-user');
      expect(callData.latencyMs).toBeGreaterThanOrEqual(0);
    });

    it('should handle OpenAI-style token usage with snake_case', () => {
      const runId = 'test-run-id';

      handler.handleLLMStart({ kwargs: { model: 'gpt-4' } }, ['Hello'], runId);

      const output = {
        llmOutput: {
          model: 'gpt-4',
          token_usage: {
            prompt_tokens: 15,
            completion_tokens: 25,
          },
        },
        generations: [],
      };

      handler.handleLLMEnd(output, runId);

      const callData = (mockDiagnyx.trackCall as any).mock.calls[0][0] as LLMCallData;
      expect(callData.inputTokens).toBe(15);
      expect(callData.outputTokens).toBe(25);
    });

    it('should handle Anthropic-style token usage', () => {
      const runId = 'test-run-id';

      handler.handleLLMStart({ kwargs: { model: 'claude-3-opus' } }, ['Hello'], runId);

      const output = {
        llmOutput: {
          model: 'claude-3-opus',
          usage: {
            input_tokens: 12,
            output_tokens: 18,
          },
        },
        generations: [],
      };

      handler.handleLLMEnd(output, runId);

      const callData = (mockDiagnyx.trackCall as any).mock.calls[0][0] as LLMCallData;
      expect(callData.provider).toBe('anthropic');
      expect(callData.inputTokens).toBe(12);
      expect(callData.outputTokens).toBe(18);
    });

    it('should handle missing token usage', () => {
      const runId = 'test-run-id';

      handler.handleLLMStart({ kwargs: { model: 'gpt-4' } }, ['Hello'], runId);

      const output = {
        llmOutput: {},
        generations: [],
      };

      handler.handleLLMEnd(output, runId);

      const callData = (mockDiagnyx.trackCall as any).mock.calls[0][0] as LLMCallData;
      expect(callData.inputTokens).toBe(0);
      expect(callData.outputTokens).toBe(0);
    });

    it('should handle call without start', () => {
      const runId = 'unknown-run-id';

      const output = {
        llmOutput: { modelName: 'gpt-4' },
        generations: [],
      };

      handler.handleLLMEnd(output, runId);

      const callData = (mockDiagnyx.trackCall as any).mock.calls[0][0] as LLMCallData;
      expect(callData.latencyMs).toBeUndefined();
    });
  });

  describe('handleLLMError', () => {
    it('should track LLM error', () => {
      const runId = 'test-run-id';

      handler.handleLLMStart({ kwargs: { model: 'gpt-4' } }, ['Hello'], runId);

      const error = new Error('API rate limit exceeded');
      (error as any).code = 'rate_limit_error';

      handler.handleLLMError(error, runId);

      expect(mockDiagnyx.trackCall).toHaveBeenCalledTimes(1);
      const callData = (mockDiagnyx.trackCall as any).mock.calls[0][0] as LLMCallData;

      expect(callData.status).toBe('error');
      expect(callData.errorMessage).toBe('API rate limit exceeded');
      expect(callData.errorCode).toBe('rate_limit_error');
      expect(callData.inputTokens).toBe(0);
      expect(callData.outputTokens).toBe(0);
    });

    it('should truncate long error messages', () => {
      const runId = 'test-run-id';

      handler.handleLLMStart({ kwargs: { model: 'gpt-4' } }, ['Hello'], runId);

      const longMessage = 'A'.repeat(600);
      const error = new Error(longMessage);

      handler.handleLLMError(error, runId);

      const callData = (mockDiagnyx.trackCall as any).mock.calls[0][0] as LLMCallData;
      expect(callData.errorMessage?.length).toBeLessThanOrEqual(500);
    });
  });

  describe('provider detection', () => {
    const testCases = [
      { model: 'gpt-4', expected: 'openai' },
      { model: 'gpt-3.5-turbo', expected: 'openai' },
      { model: 'o1-preview', expected: 'openai' },
      { model: 'claude-3-opus', expected: 'anthropic' },
      { model: 'claude-2', expected: 'anthropic' },
      { model: 'gemini-pro', expected: 'google' },
      { model: 'mistral-large', expected: 'mistral' },
      { model: 'mixtral-8x7b', expected: 'mistral' },
      { model: 'unknown-model', expected: 'custom' },
    ];

    testCases.forEach(({ model, expected }) => {
      it(`should detect ${expected} provider for ${model}`, () => {
        const runId = 'test-run-id';

        handler.handleLLMStart({ kwargs: { model } }, ['Hello'], runId);
        handler.handleLLMEnd({ llmOutput: { model }, generations: [] }, runId);

        const callData = (mockDiagnyx.trackCall as any).mock.calls[0][0] as LLMCallData;
        expect(callData.provider).toBe(expected);

        // Reset mock for next iteration
        vi.clearAllMocks();
      });
    });
  });

  describe('content capture', () => {
    it('should capture content when enabled', () => {
      const captureHandler = new DiagnyxCallbackHandler(mockDiagnyx, {
        captureContent: true,
      });

      const runId = 'test-run-id';

      captureHandler.handleLLMStart(
        { kwargs: { model: 'gpt-4' } },
        ['What is 2+2?'],
        runId,
      );

      const output = {
        llmOutput: { modelName: 'gpt-4', tokenUsage: { promptTokens: 5, completionTokens: 3 } },
        generations: [[{ text: '2+2 equals 4.' }]],
      };

      captureHandler.handleLLMEnd(output, runId);

      const callData = (mockDiagnyx.trackCall as any).mock.calls[0][0] as LLMCallData;
      expect(callData.fullPrompt).toBe('What is 2+2?');
      expect(callData.fullResponse).toBe('2+2 equals 4.');
    });

    it('should not capture content when disabled', () => {
      const runId = 'test-run-id';

      handler.handleLLMStart(
        { kwargs: { model: 'gpt-4' } },
        ['What is 2+2?'],
        runId,
      );

      const output = {
        llmOutput: { modelName: 'gpt-4' },
        generations: [[{ text: '2+2 equals 4.' }]],
      };

      handler.handleLLMEnd(output, runId);

      const callData = (mockDiagnyx.trackCall as any).mock.calls[0][0] as LLMCallData;
      expect(callData.fullPrompt).toBeUndefined();
      expect(callData.fullResponse).toBeUndefined();
    });
  });

  describe('chain callbacks (no-ops)', () => {
    it('should not throw on chain start', () => {
      expect(() => {
        handler.handleChainStart({}, {}, 'run-id');
      }).not.toThrow();
    });

    it('should not throw on chain end', () => {
      expect(() => {
        handler.handleChainEnd({}, 'run-id');
      }).not.toThrow();
    });

    it('should not throw on chain error', () => {
      expect(() => {
        handler.handleChainError(new Error('test'), 'run-id');
      }).not.toThrow();
    });
  });

  describe('tool callbacks (no-ops)', () => {
    it('should not throw on tool start', () => {
      expect(() => {
        handler.handleToolStart({}, 'input', 'run-id');
      }).not.toThrow();
    });

    it('should not throw on tool end', () => {
      expect(() => {
        handler.handleToolEnd('output', 'run-id');
      }).not.toThrow();
    });

    it('should not throw on tool error', () => {
      expect(() => {
        handler.handleToolError(new Error('test'), 'run-id');
      }).not.toThrow();
    });
  });

  describe('other callbacks (no-ops)', () => {
    it('should not throw on text', () => {
      expect(() => {
        handler.handleText('streaming text', 'run-id');
      }).not.toThrow();
    });

    it('should not throw on retry', () => {
      expect(() => {
        handler.handleRetry({}, 'run-id');
      }).not.toThrow();
    });
  });

  describe('concurrent calls', () => {
    it('should handle multiple concurrent calls correctly', () => {
      const runId1 = 'run-1';
      const runId2 = 'run-2';

      // Start both calls
      handler.handleLLMStart({ kwargs: { model: 'gpt-4' } }, ['First'], runId1);
      handler.handleLLMStart({ kwargs: { model: 'claude-3' } }, ['Second'], runId2);

      // End in reverse order
      handler.handleLLMEnd(
        { llmOutput: { modelName: 'claude-3', tokenUsage: { promptTokens: 5, completionTokens: 10 } }, generations: [] },
        runId2,
      );
      handler.handleLLMEnd(
        { llmOutput: { modelName: 'gpt-4', tokenUsage: { promptTokens: 8, completionTokens: 15 } }, generations: [] },
        runId1,
      );

      expect(mockDiagnyx.trackCall).toHaveBeenCalledTimes(2);

      const calls = (mockDiagnyx.trackCall as any).mock.calls.map((c: any) => c[0] as LLMCallData);
      const models = new Set(calls.map((c: LLMCallData) => c.model));

      expect(models.has('gpt-4')).toBe(true);
      expect(models.has('claude-3')).toBe(true);
    });
  });
});
