"use client";

import { Eye, EyeOff, Info, KeyRound, Loader2, Save, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { client } from "@/client/client.gen";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const ENDPOINT = "/api/v1/prompt-refactor-config";

interface ConfigState {
    api_key: string | null;
    is_configured: boolean;
}

async function apiGet(): Promise<ConfigState> {
    const res = await client.get({ url: ENDPOINT });
    if (res.error) throw new Error(String(res.error));
    return res.data as ConfigState;
}

async function apiPut(apiKey: string): Promise<ConfigState> {
    const res = await client.put({ url: ENDPOINT, body: { api_key: apiKey } });
    if (res.error) throw new Error(String(res.error));
    return res.data as ConfigState;
}

async function apiDelete(): Promise<void> {
    const res = await client.delete({ url: ENDPOINT });
    if (res.error) throw new Error(String(res.error));
}

export default function PromptRefactorModelPage() {
    const [config, setConfig] = useState<ConfigState>({ api_key: null, is_configured: false });
    const [inputKey, setInputKey] = useState("");
    const [showKey, setShowKey] = useState(false);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [deleting, setDeleting] = useState(false);

    const fetchConfig = useCallback(async () => {
        setLoading(true);
        try {
            const data = await apiGet();
            setConfig(data);
            setInputKey(data.api_key ?? "");
        } catch {
            toast.error("Failed to load configuration");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchConfig();
    }, [fetchConfig]);

    const handleSave = async () => {
        const trimmed = inputKey.trim();
        if (!trimmed) {
            toast.error("Please enter an API key");
            return;
        }
        setSaving(true);
        try {
            const data = await apiPut(trimmed);
            setConfig(data);
            setInputKey(data.api_key ?? "");
            toast.success("API key saved", { description: "Prompt Refactor Model configured." });
        } catch (e: unknown) {
            toast.error("Save failed", {
                description: e instanceof Error ? e.message : "Unknown error",
            });
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async () => {
        setDeleting(true);
        try {
            await apiDelete();
            setConfig({ api_key: null, is_configured: false });
            setInputKey("");
            toast.success("API key removed");
        } catch {
            toast.error("Failed to remove key");
        } finally {
            setDeleting(false);
        }
    };

    return (
        <div className="mx-auto max-w-2xl space-y-6 p-6">
            {/* Page header */}
            <div className="space-y-1">
                <h1 className="text-2xl font-semibold tracking-tight">Prompt Refactor Model</h1>
                <p className="text-sm text-muted-foreground">
                    Configure the OpenAI API key used to intelligently rewrite Agent Builder
                    prompts when you create a <strong>Chat Agent</strong> or{" "}
                    <strong>Call+Chat Agent</strong>.
                </p>
            </div>

            {/* Info banner */}
            <div className="flex gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-200">
                <Info className="mt-0.5 h-4 w-4 shrink-0" />
                <p>
                    When you build a Chat or Call+Chat agent, the Agent Builder generates
                    voice-biased prompts. This model rewrites them to be channel-aware — no
                    manual editing needed. The key is used <strong>only at agent creation
                    time</strong> and does not affect live agent runs.
                </p>
            </div>

            {/* API Key card */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                        <KeyRound className="h-4 w-4 text-muted-foreground" />
                        OpenAI API Key
                    </CardTitle>
                    <CardDescription>
                        Your key is stored securely and only the last 4 characters are shown
                        after saving. Supports any OpenAI-compatible key (e.g.{" "}
                        <code className="rounded bg-muted px-1 text-xs">sk-…</code>).
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    {loading ? (
                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            Loading…
                        </div>
                    ) : (
                        <>
                            <div className="space-y-2">
                                <Label htmlFor="prompt-refactor-api-key">API Key</Label>
                                <div className="relative flex items-center">
                                    <Input
                                        id="prompt-refactor-api-key"
                                        type={showKey ? "text" : "password"}
                                        placeholder="sk-..."
                                        value={inputKey}
                                        onChange={(e) => setInputKey(e.target.value)}
                                        className="pr-10 font-mono text-sm"
                                        autoComplete="off"
                                        spellCheck={false}
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowKey((v) => !v)}
                                        className="absolute right-3 text-muted-foreground hover:text-foreground"
                                        aria-label={showKey ? "Hide API key" : "Show API key"}
                                    >
                                        {showKey ? (
                                            <EyeOff className="h-4 w-4" />
                                        ) : (
                                            <Eye className="h-4 w-4" />
                                        )}
                                    </button>
                                </div>
                                {config.is_configured && (
                                    <p className="text-xs text-emerald-600 dark:text-emerald-400">
                                        ✓ A key is currently saved. The field shows the masked version.
                                    </p>
                                )}
                            </div>

                            <div className="flex gap-2">
                                <Button
                                    id="save-prompt-refactor-key"
                                    onClick={handleSave}
                                    disabled={saving || !inputKey.trim()}
                                    className="gap-2"
                                >
                                    {saving ? (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                        <Save className="h-4 w-4" />
                                    )}
                                    Save Key
                                </Button>

                                {config.is_configured && (
                                    <Button
                                        id="delete-prompt-refactor-key"
                                        variant="destructive"
                                        onClick={handleDelete}
                                        disabled={deleting}
                                        className="gap-2"
                                    >
                                        {deleting ? (
                                            <Loader2 className="h-4 w-4 animate-spin" />
                                        ) : (
                                            <Trash2 className="h-4 w-4" />
                                        )}
                                        Remove
                                    </Button>
                                )}
                            </div>
                        </>
                    )}
                </CardContent>
            </Card>

            {/* Model info */}
            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Model Settings</CardTitle>
                    <CardDescription>
                        Uses <strong>gpt-4.1-mini</strong> via{" "}
                        <code className="rounded bg-muted px-1 text-xs">
                            https://api.openai.com/v1
                        </code>
                        . The rewrite is a single background call per node prompt — fast and
                        inexpensive. You will be charged by OpenAI at your normal token rate.
                    </CardDescription>
                </CardHeader>
            </Card>
        </div>
    );
}
