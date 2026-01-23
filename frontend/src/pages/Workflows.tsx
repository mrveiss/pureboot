import {
  Workflow as WorkflowIcon,
  Cpu,
  Monitor,
  FileCode,
  Terminal,
} from 'lucide-react'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Badge,
} from '@/components/ui'
import { useWorkflows } from '@/hooks'
import { ARCHITECTURE_LABELS, BOOT_MODE_LABELS } from '@/types'

export function Workflows() {
  const { data: response, isLoading, error } = useWorkflows()

  const workflows = response?.data ?? []

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h2 className="text-3xl font-bold tracking-tight">Workflows</h2>
        <div className="text-muted-foreground">Loading workflows...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-6">
        <h2 className="text-3xl font-bold tracking-tight">Workflows</h2>
        <Card>
          <CardContent className="pt-6">
            <div className="text-center text-destructive">
              Failed to load workflows. Check that the workflows directory is configured.
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold tracking-tight">Workflows</h2>
      </div>

      <p className="text-muted-foreground">
        Workflows define the boot configuration for nodes. They are loaded from YAML files
        in the workflows directory.
      </p>

      {workflows.length === 0 ? (
        <Card>
          <CardContent className="pt-6">
            <div className="text-center text-muted-foreground">
              <WorkflowIcon className="mx-auto h-12 w-12 mb-4 opacity-50" />
              <p>No workflows configured.</p>
              <p className="text-sm mt-1">
                Add workflow YAML files to the workflows directory to get started.
              </p>
              <pre className="mt-4 text-left text-xs bg-muted p-4 rounded-lg inline-block">
{`# Example: workflows/ubuntu-2404.yaml
id: ubuntu-2404
name: Ubuntu 24.04 LTS
kernel_path: /tftp/ubuntu/vmlinuz
initrd_path: /tftp/ubuntu/initrd
cmdline: ip=dhcp
architecture: x86_64
boot_mode: uefi`}
              </pre>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {workflows.map((workflow) => (
            <Card key={workflow.id}>
              <CardHeader className="pb-2">
                <CardTitle className="text-lg flex items-center gap-2">
                  <WorkflowIcon className="h-5 w-5" />
                  {workflow.name}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex gap-2">
                  <Badge variant="secondary" className="flex items-center gap-1">
                    <Cpu className="h-3 w-3" />
                    {ARCHITECTURE_LABELS[workflow.architecture] || workflow.architecture}
                  </Badge>
                  <Badge variant="outline" className="flex items-center gap-1">
                    <Monitor className="h-3 w-3" />
                    {BOOT_MODE_LABELS[workflow.boot_mode] || workflow.boot_mode}
                  </Badge>
                </div>

                <div className="space-y-2 text-sm">
                  <div className="flex items-start gap-2">
                    <FileCode className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
                    <div className="min-w-0">
                      <div className="text-muted-foreground text-xs">Kernel</div>
                      <div className="font-mono text-xs truncate" title={workflow.kernel_path}>
                        {workflow.kernel_path}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-start gap-2">
                    <FileCode className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
                    <div className="min-w-0">
                      <div className="text-muted-foreground text-xs">Initrd</div>
                      <div className="font-mono text-xs truncate" title={workflow.initrd_path}>
                        {workflow.initrd_path}
                      </div>
                    </div>
                  </div>

                  {workflow.cmdline && (
                    <div className="flex items-start gap-2">
                      <Terminal className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
                      <div className="min-w-0">
                        <div className="text-muted-foreground text-xs">Command Line</div>
                        <div className="font-mono text-xs truncate" title={workflow.cmdline}>
                          {workflow.cmdline}
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                <div className="pt-2 border-t">
                  <code className="text-xs text-muted-foreground">ID: {workflow.id}</code>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
