'use client';

import { useState, useEffect, useRef } from 'react';
import Image from 'next/image';
import {
  Heart,
  Pencil,
  Trash2,
  X,
  Loader2,
  RefreshCw,
  RotateCcw,
  RotateCw,
  Eraser,
  Undo2,
  ImagePlus,
  ChevronLeft,
  ChevronRight,
  Plus,
  Star,
  ImageIcon,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { useUpdateItem, useDeleteItem, useReanalyzeItem, useRotateImage, useRemoveBackground, useRestoreOriginal, useReplaceItemImage, useAddItemImage, useDeleteItemImage, useSetPrimaryImage, useDetectCalibration, useApplyCalibration, useManualWhiteBalance, useResetCalibration, type CalibrationItem, type CalibrationDetection } from '@/lib/hooks/use-items';
import { CLOTHING_SUBTYPES, Item } from '@/lib/types';
import {
  useBodyParts,
  useClothingColors,
  useClothingTypes,
  useStyles,
  useSeasons,
  useFormalityLabel,
  useMaterialLabel,
  useSubtypeLabel,
} from '@/lib/hooks/use-translated-constants';

import { normalizePurchaseDate } from '@/lib/purchase-date';
import {
  editFormFromItem,
  type EditForm,
} from '@/lib/item-edit-form';
import { useVocabManagement } from '@/lib/hooks/use-vocabulary';
import { VocabAddDialog } from '@/components/vocab/vocab-add-dialog';
import { ImagePipelineSteps, type CalibrationState } from '@/components/image-pipeline-steps';
import { ReferenceBoxEditor, type Baseline, type Detection, type ReferenceBox } from '@/components/reference-box-editor';
import MaskBrushCanvas from '@/components/mask-brush-canvas';
// 摘不删（spec §7）：配搭生成对话框已归档至 components/dormant/，入口下线。
// import { GeneratePairingsDialog } from '@/components/dormant/generate-pairings-dialog';
import { ItemEditForm } from '@/components/item-detail/item-edit-form';
import { ItemViewDetails } from '@/components/item-detail/item-view-details';
import { useFeatures } from '@/lib/hooks/use-features';
import { useTranslations } from 'next-intl';

interface ItemDetailDialogProps {
  item: Item | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// detect 端点回 [l,t,r,b]（含右下），框选器吃对象坐标；换算只在这里，不做 ±1
function cornersToBox(corners: [number, number, number, number]): ReferenceBox {
  const [l, t, r, b] = corners;
  return { l, t, r, b };
}

// Images now use signed URLs from backend (item.image_url, item.thumbnail_url)

export function ItemDetailDialog({ item, open, onOpenChange }: ItemDetailDialogProps) {
  const t = useTranslations('wardrobe.itemDetail');
  const tc = useTranslations('common');
  const tw = useTranslations('wardrobe');
  const bodyParts = useBodyParts();
  const typeEntries = useClothingTypes();
  const colorOptions = useClothingColors();
  const styleOptions = useStyles();
  const seasons = useSeasons();
  const vocab = useVocabManagement();
  const subtypeLabel = useSubtypeLabel();
  const materialLabel = useMaterialLabel();
  const formalityLabel = useFormalityLabel();
  const [isEditing, setIsEditing] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  // 摘不删（spec §7）：配搭/建议入口已下线（suggest/pairings 休眠）。
  // const [showPairingsDialog, setShowPairingsDialog] = useState(false);
  const [imageKey, setImageKey] = useState(0);
  const [editForm, setEditForm] = useState<EditForm>({
    name: '',
    type: '',
    body_part: '',
    subtype: '',
    brand: '',
    primary_colors: [],
    secondary_colors: [],
    style: [],
    season: [],
    temp_low: undefined,
    temp_high: undefined,
    purchase_date: '',
    purchase_price: undefined,
    lifecycle: 'active',
    is_archived: false,
    archive_reason: '',
    notes: '',
    favorite: false,
    wash_interval: undefined,
  });
  const [activeImageIndex, setActiveImageIndex] = useState(0);
  // 图片管线会话态（R38）：校色状态不落库——ClothingItem 没有校色状态列，
  // 拿工作图与 calibration_original_path 比对是假信号。对话框打开/换 item 归
  // 'none'；检测没检出归 'skipped'；应用成功归 'done'。刷新页面即重来，反正
  // 「重置回原图」一直可点。
  const [calibration, setCalibration] = useState<CalibrationState>('none');
  const [detection, setDetection] = useState<Detection | null>(null);
  const [showManualWb, setShowManualWb] = useState(false);
  const [kelvin, setKelvin] = useState(6500);
  const [tint, setTint] = useState(0);
  const [showBrush, setShowBrush] = useState(false);
  // D2 门禁的本地依据：item.mask_path 非空即「有抠图」；mask_cleared 时先本地置
  // false（R21a），等 refetch 的 mask_path 变 null 追上，不冲突。
  const [hasMask, setHasMask] = useState(Boolean(item?.mask_path));

  const updateItem = useUpdateItem();
  const deleteItem = useDeleteItem();
  const reanalyzeItem = useReanalyzeItem();
  const rotateImage = useRotateImage();
  const removeBackground = useRemoveBackground();
  const restoreOriginal = useRestoreOriginal();
  const replaceImage = useReplaceItemImage();
  const replaceImageInputRef = useRef<HTMLInputElement>(null);
  const { data: features } = useFeatures();
  // 摘不删（spec §7）：洗衣跟踪入口已下线（POST /items/{id}/wash 与
  // /wash-history 均已摘挂），hooks 保留在 use-items 里备查。
  // const logWash = useLogWash();
  // const { data: washHistory } = useWashHistory(item?.id || '');
  const addImage = useAddItemImage();
  const deleteImage = useDeleteItemImage();
  const setPrimary = useSetPrimaryImage();
  const detectCalibration = useDetectCalibration();
  const applyCalibration = useApplyCalibration();
  const manualWb = useManualWhiteBalance();
  const resetCalibration = useResetCalibration();

  useEffect(() => {
    if (item) {
      setEditForm(editFormFromItem(item, typeEntries));
      setIsEditing(false);
      setActiveImageIndex(0);
      // 换 item 就是新的会话：校色状态/框选/滑块/画笔全部重来
      setCalibration('none');
      setDetection(null);
      setShowManualWb(false);
      setShowBrush(false);
    }
  }, [item?.id]);

  useEffect(() => {
    setHasMask(Boolean(item?.mask_path));
  }, [item?.id, item?.mask_path]);

  if (!item) return null;

  const handleSave = async () => {
    if (editForm.primary_colors.length === 0) {
      toast.error(t('primaryColorRequired'));
      return;
    }
    let purchaseDate: string | null = null;
    try {
      // null (not undefined) so clearing the field actually clears it server-side.
      purchaseDate = normalizePurchaseDate(editForm.purchase_date) || null;
    } catch {
      toast.error(t('invalidPurchaseDate'));
      return;
    }
    try {
      await updateItem.mutateAsync({
        id: item.id,
        data: {
          name: editForm.name || undefined,
          type: editForm.type,
          body_part: editForm.body_part || null,
          // null (not undefined) so clearing the field actually clears it server-side.
          subtype: editForm.subtype.trim() || null,
          brand: editForm.brand || undefined,
          primary_colors: editForm.primary_colors,
          secondary_colors: editForm.secondary_colors,
          temp_low: editForm.temp_low ?? null,
          temp_high: editForm.temp_high ?? null,
          purchase_date: purchaseDate,
          purchase_price: editForm.purchase_price ?? null,
          lifecycle: editForm.lifecycle,
          is_archived: editForm.lifecycle === 'retired',
          archive_reason: editForm.lifecycle === 'retired' ? editForm.archive_reason.trim() || null : null,
          notes: editForm.notes || undefined,
          favorite: editForm.favorite,
          wash_interval: editForm.wash_interval,
          // Style/season keep the tags submit path; the backend projects them onto the columns.
          // wear_count is deliberately NOT sent (Ruling 68): the form's stale value must not
          // overwrite a count that records just adjusted.
          tags: { ...item.tags, style: editForm.style, season: editForm.season },
        },
      });
      setIsEditing(false);
    } catch (error) {
      console.error('Failed to update item:', error);
    }
  };

  // 摘不删（spec §7）：与上面的 hooks 一并下线。
  // const handleMarkWashed = async () => {
  //   try {
  //     await logWash.mutateAsync({ id: item.id });
  //     toast.success(t('actions.washed'));
  //   } catch (error) {
  //     console.error('Failed to log wash:', error);
  //     toast.error(t('actions.washError'));
  //   }
  // };

  const handleDelete = async () => {
    try {
      await deleteItem.mutateAsync(item.id);
      setShowDeleteConfirm(false);
      onOpenChange(false);
      toast.success(t('actions.deleted'), {
        description: item.name ? t('actions.deletedWithName', { name: item.name }) : t('actions.deletedFallback'),
      });
    } catch (error) {
      console.error('Failed to delete item:', error);
      toast.error(t('actions.deleteError'), {
        description: t('actions.deleteErrorDescription'),
      });
    }
  };

  const handleToggleFavorite = async () => {
    try {
      await updateItem.mutateAsync({
        id: item.id,
        data: { favorite: !item.favorite },
      });
    } catch (error) {
      console.error('Failed to toggle favorite:', error);
    }
  };

  const handleReanalyze = async () => {
    try {
      const result = await reanalyzeItem.mutateAsync(item.id);
      if (result.status === 'cooldown' && result.retry_after_seconds) {
        toast.info(tw('ai.retryCooldown', { seconds: result.retry_after_seconds }));
      }
      // Otherwise status will update to 'processing' and UI will reflect it
    } catch (error) {
      console.error('Failed to trigger re-analysis:', error);
    }
  };

  // 图像被改写（旋转/还原/替换/换主图）后，旧检出框不再对应像素：清框，
  // 并把依附它的 'pending' 退回 'none'（done/skipped 是已发生的事实，保留）。
  const clearStaleDetection = () => {
    setDetection(null);
    setCalibration((c) => (c === 'pending' ? 'none' : c));
  };

  const handleRotate = async (direction: 'cw' | 'ccw') => {
    try {
      await rotateImage.mutateAsync({ id: item.id, direction });
      setImageKey((k) => k + 1);
      clearStaleDetection();
      toast.success(t('actions.imageRotated'));
    } catch (error) {
      console.error('Failed to rotate image:', error);
      toast.error(t('actions.imageRotateError'));
    }
  };

  const handleRemoveBackground = async () => {
    try {
      const result = await removeBackground.mutateAsync({ id: item.id });
      setImageKey((k) => k + 1);
      // 抠图落盘即有 mask，D2 的打标门禁随之打开
      setHasMask(Boolean(result.mask_path));
      toast.success(t('actions.backgroundRemoved'));
    } catch (error) {
      console.error('Failed to remove background:', error);
      toast.error(t('actions.backgroundRemoveError'));
    }
  };

  const handleRestoreOriginal = async () => {
    try {
      await restoreOriginal.mutateAsync(item.id);
      setImageKey((k) => k + 1);
      clearStaleDetection();
      toast.success(t('actions.originalRestored'));
    } catch (error) {
      console.error('Failed to restore original image:', error);
      toast.error(t('actions.originalRestoreError'));
    }
  };

  const handleReplaceImage = async (file: File) => {
    try {
      await replaceImage.mutateAsync({ itemId: item.id, file });
      setImageKey((k) => k + 1);
      clearStaleDetection();
      setActiveImageIndex(0);
      toast.success(t('actions.imageReplaced'));
    } catch (error) {
      console.error('Failed to replace image:', error);
      toast.error(t('actions.imageReplaceError'));
    }
  };

  // R21a：mask_cleared 的唯一用途——本次校色把 mask 打掉了，弹提示并清本地 hasMask
  const handleMaskCleared = (result: CalibrationItem) => {
    if (result.mask_cleared) {
      setHasMask(false);
      setShowBrush(false);
      toast.warning(tw('pipeline.maskCleared'));
    }
  };

  const handleCalibrate = async () => {
    if (detectCalibration.isPending) return;
    try {
      const found = await detectCalibration.mutateAsync(item.id);
      if (!found.kind || !found.box) {
        // 检不出参考卡：跳过自动校色、不猜白平衡（spec §1.4），走色温/色调兜底
        setDetection(null);
        setCalibration('skipped');
        setShowManualWb(true);
        return;
      }
      const cards = found.cards;
      setCalibration('pending');
      setDetection({
        kind: found.kind,
        box: cornersToBox(found.box),
        cards: cards
          ? {
              ...(cards.white ? { white: cornersToBox(cards.white) } : {}),
              ...(cards.gray ? { gray: cornersToBox(cards.gray) } : {}),
              ...(cards.black ? { black: cornersToBox(cards.black) } : {}),
            }
          : undefined,
      });
    } catch (error) {
      console.error('Failed to detect calibration reference:', error);
      toast.error(tw('pipeline.calibrateError'));
    }
  };

  const handleApplyBox = async (box: ReferenceBox, baseline: Baseline) => {
    try {
      // 含右下契约：四元组原样回传，唯一的 +1 在后端 calibrate 内部（R35）
      const result = await applyCalibration.mutateAsync({
        id: item.id,
        box: [box.l, box.t, box.r, box.b],
        baseline,
      });
      setCalibration('done');
      setDetection(null);
      handleMaskCleared(result);
      setImageKey((k) => k + 1);
    } catch (error) {
      console.error('Failed to apply calibration:', error);
      toast.error(tw('pipeline.applyError'));
    }
  };

  const handleManualWb = async () => {
    try {
      const result = await manualWb.mutateAsync({ id: item.id, kelvin, tint });
      setCalibration('done');
      setDetection(null);
      setShowManualWb(false);
      handleMaskCleared(result);
      setImageKey((k) => k + 1);
    } catch (error) {
      console.error('Failed to apply manual white balance:', error);
      toast.error(tw('pipeline.manualWbError'));
    }
  };

  const handleResetCalibration = async () => {
    try {
      const result = await resetCalibration.mutateAsync(item.id);
      setCalibration('none');
      setDetection(null);
      setShowManualWb(false);
      handleMaskCleared(result);
      setImageKey((k) => k + 1);
    } catch (error) {
      console.error('Failed to reset calibration:', error);
      toast.error(tw('pipeline.resetError'));
    }
  };

  // Manual tagging trigger (D2): POST /items/{id}/analyze actually enqueues the job.
  const handleRetag = async () => {
    try {
      const result = await reanalyzeItem.mutateAsync(item.id);
      if (result.status === 'deferred') {
        toast.info(tw('pipeline.retagDeferred'));
      } else if (result.status === 'cooldown') {
        toast.info(tw('ai.retryCooldown', { seconds: result.retry_after_seconds ?? 0 }));
      } else {
        toast.success(tw('pipeline.retagQueued'));
      }
    } catch (error) {
      console.error('Failed to start tagging:', error);
      toast.error(tw('pipeline.retagError'));
    }
  };

  const isAnalyzing = reanalyzeItem.isPending || item.status === 'processing';

  // Use signed URL from backend for better quality in detail view
  const imageUrl = item.image_url || item.image_path;
  const typeInfo = typeEntries.find((entry) => entry.value === item.type);
  const colorLabel = (value: string) => colorOptions.find((c) => c.value === value);
  const primaryColorInfo = (item.primary_colors ?? []).map(colorLabel);
  const secondaryColorInfo = (item.secondary_colors ?? []).map(colorLabel);
  const unrecognizedType = item.type === 'unknown' ? item.ai_unrecognized_type : null;
  const subtypeSuggestions = CLOTHING_SUBTYPES[editForm.type] ?? [];

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-2xl max-h-[90vh] flex flex-col p-0 overflow-hidden [&>button]:hidden">
          {/* Header - sticky */}
          <DialogHeader className="flex flex-row items-center gap-2 space-y-0 p-4 border-b flex-shrink-0">
            {/* Below sm the title keeps its 45% cap and the actions stay in a
                scrollable row, so the close control is always reachable on a
                phone. From sm up the title becomes the flexible item and the
                actions row is sized to its content instead, so every action
                stays visible and the name truncates. Previously the title had
                no cap at all from sm up: because a flex item claims its content
                width before a flex-1 sibling does, a long name squeezed the
                actions row and pushed edit and replace-image out of view. */}
            <DialogTitle className="text-xl min-w-0 truncate max-w-[45%] sm:max-w-none sm:flex-1">
              {item.name || (typeInfo ? typeInfo.label : item.type)}
            </DialogTitle>
            {/* The action row scrolls sideways once it stops fitting, because
                the dialog clips its own overflow: without this the buttons
                push the close control past the right edge on a phone and it
                cannot be reached at all. */}
            <div className="flex-1 min-w-0 overflow-x-auto overscroll-x-contain [scrollbar-width:none] [&::-webkit-scrollbar]:hidden sm:flex-none">
              <div className="flex w-max ml-auto items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleToggleFavorite}
                  disabled={updateItem.isPending}
                  title={t('titles.toggleFavorite')}
                >
                  <Heart
                    className={`h-5 w-5 ${
                      item.favorite ? 'fill-red-500 text-red-500' : 'text-muted-foreground'
                    }`}
                  />
                </Button>
                {/* 摘不删（spec §7）：「找搭配 / 建议搭配」入口已下线——suggest/pairings 休眠。 */}
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleReanalyze}
                  disabled={isAnalyzing}
                  title={isAnalyzing ? t('titles.analysisInProgress') : t('titles.reanalyzeWithAI')}
                >
                  <RefreshCw
                    className={`h-5 w-5 ${isAnalyzing ? 'animate-spin text-primary' : ''}`}
                  />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => handleRotate('ccw')}
                  disabled={rotateImage.isPending}
                  title={t('titles.rotateLeft')}
                >
                  {rotateImage.isPending ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    <RotateCcw className="h-5 w-5" />
                  )}
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => handleRotate('cw')}
                  disabled={rotateImage.isPending}
                  title={t('titles.rotateRight')}
                >
                  {rotateImage.isPending ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    <RotateCw className="h-5 w-5" />
                  )}
                </Button>
                {features?.background_removal && (
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={handleRemoveBackground}
                    disabled={removeBackground.isPending || !item.image_url}
                    title={t('titles.removeBackground')}
                  >
                    {removeBackground.isPending ? (
                      <Loader2 className="h-5 w-5 animate-spin" />
                    ) : (
                      <Eraser className="h-5 w-5" />
                    )}
                  </Button>
                )}
                {item.original_image_path && (
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={handleRestoreOriginal}
                    disabled={restoreOriginal.isPending}
                    title={t('titles.undoBackgroundRemoval')}
                  >
                    {restoreOriginal.isPending ? (
                      <Loader2 className="h-5 w-5 animate-spin" />
                    ) : (
                      <Undo2 className="h-5 w-5" />
                    )}
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => replaceImageInputRef.current?.click()}
                  disabled={replaceImage.isPending}
                  title={t('titles.replaceImage')}
                >
                  {replaceImage.isPending ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    <ImagePlus className="h-5 w-5" />
                  )}
                </Button>
                <input
                  ref={replaceImageInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) {
                      handleReplaceImage(file);
                    }
                    e.target.value = '';
                  }}
                />
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => {
                    // Re-read the item on entering edit mode: tagging can finish while the
                    // dialog is open (same id, so the effect above doesn't re-run).
                    if (!isEditing) setEditForm(editFormFromItem(item, typeEntries));
                    setIsEditing(!isEditing);
                  }}
                  title={isEditing ? t('actions.cancelEditing') : t('actions.editItem')}
                >
                  {isEditing ? (
                    <X className="h-5 w-5" />
                  ) : (
                    <Pencil className="h-5 w-5" />
                  )}
                </Button>
              </div>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onOpenChange(false)}
              className="rounded-full flex-shrink-0"
              title={tc('close')}
            >
              <X className="h-5 w-5" />
            </Button>
          </DialogHeader>

          {/* Scrollable content */}
          <div className="flex-1 overflow-y-auto overscroll-contain p-6 pt-4">
            <div className="grid gap-6 sm:grid-cols-2 [&>*]:min-w-0">
            {/* Image Gallery */}
            <div className="space-y-2">
              <div className="relative aspect-square bg-muted rounded-lg overflow-hidden">
                {(() => {
                  const allImages = [
                    { url: `${imageUrl}&v=${imageKey}`, id: 'primary' },
                    ...(item.additional_images || []).map((img) => ({ url: img.image_url, id: img.id })),
                  ];
                  const currentImage = allImages[activeImageIndex] || allImages[0];
                  return (
                    <>
                      <Image
                        key={`${currentImage.id}-${imageKey}`}
                        src={currentImage.url}
                        alt={item.name || item.type}
                        fill
                        className="object-cover"
                        sizes="(max-width: 640px) 100vw, 50vw"
                      />
                      {allImages.length > 1 && (
                        <>
                          <button
                            className="absolute left-1 top-1/2 -translate-y-1/2 bg-black/50 text-white rounded-full p-1 hover:bg-black/70"
                            onClick={() => setActiveImageIndex((i) => (i - 1 + allImages.length) % allImages.length)}
                          >
                            <ChevronLeft className="h-4 w-4" />
                          </button>
                          <button
                            className="absolute right-1 top-1/2 -translate-y-1/2 bg-black/50 text-white rounded-full p-1 hover:bg-black/70"
                            onClick={() => setActiveImageIndex((i) => (i + 1) % allImages.length)}
                          >
                            <ChevronRight className="h-4 w-4" />
                          </button>
                          <div className="absolute bottom-2 left-1/2 -translate-x-1/2 flex gap-1">
                            {allImages.map((_, idx) => (
                              <button
                                key={idx}
                                className={`w-1.5 h-1.5 rounded-full ${idx === activeImageIndex ? 'bg-white' : 'bg-white/50'}`}
                                onClick={() => setActiveImageIndex(idx)}
                              />
                            ))}
                          </div>
                        </>
                      )}
                    </>
                  );
                })()}
                {isAnalyzing && (
                  <div className="absolute inset-0 bg-black/60 flex flex-col items-center justify-center gap-2">
                    <Loader2 className="h-8 w-8 text-white animate-spin" />
                    <span className="text-white text-sm font-medium">{t('view.aiAnalyzing')}</span>
                  </div>
                )}
              </div>
              {/* Thumbnail strip */}
              {(item.additional_images?.length > 0 || isEditing) && (
                <div className="flex gap-1.5 overflow-x-auto">
                  <button
                    className={`relative w-12 h-12 rounded border-2 overflow-hidden flex-shrink-0 ${activeImageIndex === 0 ? 'border-primary' : 'border-transparent'}`}
                    onClick={() => setActiveImageIndex(0)}
                  >
                    <Image src={imageUrl} alt={t('view.primaryImage')} fill className="object-cover" sizes="48px" />
                  </button>
                  {(item.additional_images || []).map((img, idx) => (
                    <div key={img.id} className="relative flex-shrink-0">
                      <button
                        className={`relative w-12 h-12 rounded border-2 overflow-hidden ${activeImageIndex === idx + 1 ? 'border-primary' : 'border-transparent'}`}
                        onClick={() => setActiveImageIndex(idx + 1)}
                      >
                        <Image src={img.thumbnail_url || img.image_url} alt="" fill className="object-cover" sizes="48px" />
                      </button>
                      {isEditing && (
                        <div className="absolute -top-1 -right-1 flex gap-0.5">
                          <button
                            className="bg-primary text-primary-foreground rounded-full p-0.5 hover:bg-primary/90"
                            title={t('titles.setAsPrimary')}
                            onClick={() => {
                              setPrimary.mutate(
                                { itemId: item.id, imageId: img.id },
                                {
                                  onSuccess: () => {
                                    setImageKey((k) => k + 1);
                                    clearStaleDetection();
                                  },
                                },
                              );
                              setActiveImageIndex(0);
                            }}
                          >
                            <Star className="h-2.5 w-2.5" />
                          </button>
                          <button
                            className="bg-destructive text-destructive-foreground rounded-full p-0.5 hover:bg-destructive/90"
                            title={t('titles.deleteImage')}
                            onClick={() => {
                              deleteImage.mutate({ itemId: item.id, imageId: img.id });
                              if (activeImageIndex > idx) setActiveImageIndex((i) => i - 1);
                            }}
                          >
                            <X className="h-2.5 w-2.5" />
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                  {isEditing && (item.additional_images?.length || 0) < 4 && (
                    <label
                      className="w-12 h-12 rounded border-2 border-dashed border-muted-foreground/30 flex items-center justify-center cursor-pointer hover:border-primary/50 flex-shrink-0"
                    >
                      {addImage.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                      ) : (
                        <Plus className="h-4 w-4 text-muted-foreground" />
                      )}
                      <input
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) {
                            addImage.mutate({ itemId: item.id, file });
                          }
                          e.target.value = '';
                        }}
                      />
                    </label>
                  )}
                </div>
              )}
            </div>

            {/* 图片管线（spec §1.4）：校色 → 抠图 → 打标；抠图没做完不给打标（D2） */}
            <div className="space-y-2">
              <ImagePipelineSteps
                calibration={calibration}
                hasMask={hasMask}
                tagged={item.tagging_status === 'tagged'}
                onCalibrate={handleCalibrate}
                onCutout={handleRemoveBackground}
                onTag={handleRetag}
              />
              <div className="flex gap-1.5">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleResetCalibration}
                  disabled={resetCalibration.isPending}
                >
                  {tw('pipeline.reset')}
                </Button>
                {hasMask && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setShowBrush((s) => !s)}
                    aria-expanded={showBrush}
                  >
                    {tw('pipeline.editMask')}
                  </Button>
                )}
              </div>
              {detection && (
                <ReferenceBoxEditor
                  imageSrc={`${imageUrl}&v=${imageKey}`}
                  detection={detection}
                  onApply={handleApplyBox}
                  onManual={() => {
                    setDetection(null);
                    setShowManualWb(true);
                  }}
                />
              )}
              {showManualWb && (
                <div className="space-y-2 rounded-md border p-2">
                  <div className="space-y-1">
                    <Label htmlFor="wb-kelvin">{tw('pipeline.kelvin')}</Label>
                    <input
                      id="wb-kelvin"
                      type="range"
                      min={1500}
                      max={15000}
                      step={100}
                      value={kelvin}
                      onChange={(e) => setKelvin(Number(e.target.value))}
                      className="w-full"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="wb-tint">{tw('pipeline.tint')}</Label>
                    <input
                      id="wb-tint"
                      type="range"
                      min={-100}
                      max={100}
                      step={1}
                      value={tint}
                      onChange={(e) => setTint(Number(e.target.value))}
                      className="w-full"
                    />
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    onClick={handleManualWb}
                    disabled={manualWb.isPending}
                  >
                    {tw('pipeline.apply')}
                  </Button>
                </div>
              )}
              {showBrush && hasMask && (
                <MaskBrushCanvas
                  imageSrc={`${imageUrl}&v=${imageKey}`}
                  itemId={item.id}
                  onSaved={() => setImageKey((k) => k + 1)}
                />
              )}
            </div>

            {/* Details */}
            <div className="space-y-4">
              {isEditing ? (
                <ItemEditForm
                  item={item}
                  form={editForm}
                  setForm={setEditForm}
                  bodyParts={bodyParts}
                  typeEntries={typeEntries}
                  colorOptions={colorOptions}
                  styleOptions={styleOptions}
                  seasons={seasons}
                  vocab={vocab}
                  subtypeLabel={subtypeLabel}
                  subtypeSuggestions={subtypeSuggestions}
                  unrecognizedType={unrecognizedType}
                  imageUrl={imageUrl}
                  isSaving={updateItem.isPending}
                  onSave={handleSave}
                  onCancel={() => setIsEditing(false)}
                />
              ) : (
                <ItemViewDetails
                  item={item}
                  typeInfo={typeInfo}
                  colorOptions={colorOptions}
                  primaryColorInfo={primaryColorInfo}
                  secondaryColorInfo={secondaryColorInfo}
                  unrecognizedType={unrecognizedType}
                  styleOptions={styleOptions}
                  seasons={seasons}
                  subtypeLabel={subtypeLabel}
                  materialLabel={materialLabel}
                  formalityLabel={formalityLabel}
                />
              )}
            </div>
            </div>

            {/* Delete button - separated from other actions for safety */}
            {!isEditing && (
              <div className="pt-4 border-t mt-4">
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive hover:text-destructive hover:bg-destructive/10"
                  onClick={() => setShowDeleteConfirm(true)}
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  {t('actions.deleteItem')}
                </Button>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('actions.deleteConfirm')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('actions.deleteDescription', { name: item.name || item.type })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{tc('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={deleteItem.isPending}
            >
              {deleteItem.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : null}
              {tc('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* 摘不删（spec §7）：GeneratePairingsDialog 渲染已下线，组件归档于 components/dormant/。 */}

      <VocabAddDialog
        kind={vocab.addKind ?? 'styles'}
        open={vocab.addKind !== null}
        onOpenChange={vocab.closeAdd}
        family={vocab.addKind === 'types' ? editForm.body_part || undefined : undefined}
      />
    </>
  );
}
