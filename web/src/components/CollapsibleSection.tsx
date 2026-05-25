import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Stack,
  Typography,
} from '@mui/material'
import type { ReactNode } from 'react'

export interface CollapsibleSectionProps {
  title: ReactNode
  subtitle?: ReactNode
  defaultExpanded?: boolean
  actions?: ReactNode
  children: ReactNode
}

export function CollapsibleSection({
  title,
  subtitle,
  defaultExpanded = false,
  actions,
  children,
}: CollapsibleSectionProps) {
  return (
    <Accordion
      defaultExpanded={defaultExpanded}
      disableGutters
      sx={{
        bgcolor: 'background.paper',
        boxShadow: 'none',
        '&::before': { display: 'none' },
        border: 1,
        borderColor: 'divider',
        borderRadius: 1,
        '&.Mui-expanded': { margin: 0 },
        overflow: 'hidden',
      }}
    >
      <AccordionSummary
        expandIcon={<ExpandMoreIcon />}
        sx={{ minHeight: 48, '& .MuiAccordionSummary-content': { my: 1 } }}
      >
        <Stack
          direction="row"
          spacing={1}
          sx={{ alignItems: 'center', justifyContent: 'space-between', width: '100%', pr: 1 }}
        >
          <Box sx={{ minWidth: 0 }}>
            {typeof title === 'string' ? (
              <Typography variant="subtitle1">{title}</Typography>
            ) : (
              title
            )}
            {subtitle &&
              (typeof subtitle === 'string' ? (
                <Typography variant="body2" color="text.secondary" noWrap>
                  {subtitle}
                </Typography>
              ) : (
                subtitle
              ))}
          </Box>
          {actions && (
            <Box
              onClick={(event) => event.stopPropagation()}
              onFocus={(event) => event.stopPropagation()}
              sx={{ flexShrink: 0 }}
            >
              {actions}
            </Box>
          )}
        </Stack>
      </AccordionSummary>
      <AccordionDetails sx={{ px: 2, pb: 2, pt: 0 }}>{children}</AccordionDetails>
    </Accordion>
  )
}
