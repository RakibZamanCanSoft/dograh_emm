'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { createWorkflowFromTemplateApiV1WorkflowCreateTemplatePost } from '@/client/sdk.gen';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { useAuth } from '@/lib/auth';
import logger from '@/lib/logger';

type AgentType = 'inbound' | 'outbound' | 'chat' | 'call_and_chat';

const AGENT_TYPE_OPTIONS: { value: AgentType; label: string; description: string }[] = [
    {
        value: 'inbound',
        label: 'Inbound Call (Users call AI)',
        description: 'Users will call your AI agent by phone or WebRTC.',
    },
    {
        value: 'outbound',
        label: 'Outbound Call (AI calls users)',
        description: 'Your AI agent will initiate phone calls to users.',
    },
    {
        value: 'chat',
        label: 'Chat Agent (Text only)',
        description: 'Users will interact with your agent via a website chat widget.',
    },
    {
        value: 'call_and_chat',
        label: 'Call + Chat Agent (Voice & Text)',
        description: 'Your agent will handle both phone calls and website chat.',
    },
];

/** Map our agent types to the call_type value the MPS API expects. */
function toCallType(agentType: AgentType): 'inbound' | 'outbound' {
    if (agentType === 'outbound') return 'outbound';
    return 'inbound';
}

export default function CreateWorkflowPage() {
    const router = useRouter();
    const { user, getAccessToken } = useAuth();
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [showSuccessModal, setShowSuccessModal] = useState(false);
    const [workflowId, setWorkflowId] = useState<string | null>(null);

    const [agentType, setAgentType] = useState<AgentType>('inbound');
    const [useCase, setUseCase] = useState('');
    const [activityDescription, setActivityDescription] = useState('');

    const selectedOption = AGENT_TYPE_OPTIONS.find((o) => o.value === agentType)!;

    const handleCreateWorkflow = async () => {
        if (!useCase || !activityDescription) {
            setError('Please fill in all fields');
            return;
        }

        if (!user) {
            setError('You must be logged in to create a workflow');
            return;
        }

        setIsLoading(true);
        setError(null);

        try {
            const accessToken = await getAccessToken();

            // Call the API to create workflow from template.
            // call_type is the required field MPS understands; agent_type carries
            // our extended concept (chat / call_and_chat) for the backend interceptor.
            const response = await createWorkflowFromTemplateApiV1WorkflowCreateTemplatePost({
                body: {
                    call_type: toCallType(agentType),
                    use_case: useCase,
                    activity_description: activityDescription,
                    // @ts-expect-error – agent_type is our custom extension not yet in the generated SDK
                    agent_type: agentType,
                },
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                },
            });

            if (response.data?.id) {
                setWorkflowId(String(response.data.id));
                setShowSuccessModal(true);
            }
        } catch (err) {
            setError('Failed to create agent. Please try again.');
            logger.error(`Error creating workflow: ${err}`);
        } finally {
            setIsLoading(false);
        }
    };

    const handleModalContinue = () => {
        if (!workflowId) return;
        router.push(`/workflow/${workflowId}?onboarding=web_call`);
    };

    return (
        <div className="min-h-screen">
            <div className="container mx-auto px-4 py-8 max-w-2xl">
                <div className="mb-6">
                    <h1 className="text-3xl font-bold mb-2">Create Agent</h1>
                    <p className="text-muted-foreground">
                        Tell us about your use case and we&apos;ll create a customized agent for you
                    </p>
                </div>

                <Card>
                    <CardHeader>
                        <CardTitle>Agent Details</CardTitle>
                        <CardDescription>
                            Configure your agent settings
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-6">
                        <div className="space-y-2">
                            <Label htmlFor="agent-type">Agent Type</Label>
                            <Select
                                value={agentType}
                                onValueChange={(value) => setAgentType(value as AgentType)}
                            >
                                <SelectTrigger id="agent-type">
                                    <SelectValue placeholder="Select agent type" />
                                </SelectTrigger>
                                <SelectContent>
                                    {AGENT_TYPE_OPTIONS.map((opt) => (
                                        <SelectItem key={opt.value} value={opt.value}>
                                            {opt.label}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                            <p className="text-sm text-muted-foreground">
                                {selectedOption.description}
                            </p>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="use-case">Use Case</Label>
                            <Input
                                id="use-case"
                                placeholder="e.g., Lead Qualification, HR Screening, Customer Support"
                                value={useCase}
                                onChange={(e) => setUseCase(e.target.value)}
                            />
                            <p className="text-sm text-muted-foreground">
                                Describe the primary purpose of your agent
                            </p>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="activity-description">Activity Description</Label>
                            <Textarea
                                id="activity-description"
                                placeholder="Describe briefly what your agent will do (e.g., Qualify leads for real estate, Screen candidates for roles, Handle customer support). This will be a prompt to an LLM."
                                value={activityDescription}
                                onChange={(e) => setActivityDescription(e.target.value)}
                                className="min-h-[100px]"
                            />
                            <p className="text-sm text-muted-foreground">
                                This description will be used to generate the AI prompt for your agent
                            </p>
                        </div>

                        {error && (
                            <p className="text-sm text-red-500">{error}</p>
                        )}

                        <div className="pt-4">
                            <Button
                                onClick={handleCreateWorkflow}
                                disabled={isLoading || !useCase || !activityDescription}
                                className="w-full"
                            >
                                {isLoading ? 'Creating...' : 'Create Agent'}
                            </Button>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Loading Overlay */}
            {isLoading && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
                    <Card className="w-full max-w-md p-8">
                        <div className="flex flex-col items-center space-y-6">
                            {/* Animated spinner */}
                            <div className="relative">
                                <div className="w-16 h-16 border-4 border-muted rounded-full"></div>
                                <div className="absolute top-0 left-0 w-16 h-16 border-4 border-transparent border-t-primary rounded-full animate-spin"></div>
                            </div>

                            <div className="text-center space-y-2">
                                <h3 className="text-lg font-semibold">
                                    Creating Your Agent
                                </h3>
                                <p className="text-sm text-muted-foreground max-w-xs">
                                    We&apos;re setting up your agent with your specifications. This will just take a moment...
                                </p>
                            </div>
                        </div>
                    </Card>
                </div>
            )}

            {/* Success Modal */}
            <Dialog open={showSuccessModal} onOpenChange={setShowSuccessModal}>
                <DialogContent className="sm:max-w-lg">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <svg className="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            Agent Created Successfully!
                        </DialogTitle>
                        <DialogDescription asChild>
                            <div className="mt-4 space-y-3">
                                <p>
                                    An agent workflow has been generated for your use case, with some artificial data and sample actions.
                                </p>
                                {(agentType === 'chat' || agentType === 'call_and_chat') && (
                                    <p>
                                        Multi-channel instructions have been added to your agent&apos;s global prompt so it behaves appropriately for both voice calls and text chat.
                                    </p>
                                )}
                                <p>
                                    Next steps would be to test the agent in the editor, and then modify it to suit your use case.
                                </p>
                            </div>
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter className="mt-6">
                        <Button
                            onClick={handleModalContinue}
                            className="w-full"
                        >
                            Open and Test Agent
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
